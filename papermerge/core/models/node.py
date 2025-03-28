import uuid
from typing import List, Tuple

from celery import current_app
from django.db import models
from django.db.models import Q
from taggit.managers import TaggableManager, _TaggableManager

from papermerge.core import validators
from papermerge.core.constants import INDEX_ADD_NODE, INDEX_REMOVE_NODE
from papermerge.core.models.tags import ColoredTag
from papermerge.core.signal_definitions import node_post_move
from papermerge.core.utils.decorators import if_redis_present

from .utils import uuid2raw_str

NODE_TYPE_FOLDER = "folder"
NODE_TYPE_DOCUMENT = "document"


def move_node(source_node, target_node):
    """
    Set `target_node` as new parent of `source_node`.

    Also send `papermerge.core.signal_definitions.node_post_move` signal
    to all interested parties. Search indexes will be interested in this
    signal as they will have to update breadcrumb of all descendants of the
    new parent.
    """
    source_node.parent = target_node
    source_node.save()
    node_post_move.send(
        sender=BaseTreeNode, instance=source_node, new_parent=target_node
    )


class PolymorphicTagManager(_TaggableManager):
    """
    What is this ugliness all about?

    `taggit` adds tags to models. Besides useful attributes of tag like
    name and color, tags also consider the "type" of the associated model.
    For example if we would add tag to Folder model - f1.add(['red', 'blue'])
    when looking up tags associated to f1 i.e. `f1.tags.all()` `taggit`
    internals will search for all tags with name 'red' and 'blue' AND
    model name `Folder` (actually django's ContentType of the model `Folder`).
    Similar for `Document` model doc.tags.all() - will look up for all tags
    associated to doc instance AND model `Document`.

    In context of Papermerge, both `Folder` and `Documents` are `BaseTreeNode`s
    as well - so when user adds tags to `Folder` or `Document` instances he/she
    expects to find same tags when looking via associated node instances.

    Example A:

        $ f1 = Folder.objects.create(...)
        $ f1.tags.add(['red', 'blue'])
        $ node = BaseTreeNode.objects.get(pk=f1.pk)     (1)
        $ node.tags.all() == f1.tags.all()              (2)

    In (1) we get associated node of the folder f1 - and in (2) we expect
    that node instance will have tags 'red' and 'blue' associated.

    The problem is that `taggit` does not work that way and without
    workaround implemented by `PolymorphicTagManager` the scenario described
    in Example A will not work - because when performing `node.tags.all()`
    default `taggit` behaviour is to consider `ContentType` of the associated
    instance - in this case `BaseTreeNode`; because tags were added via Folder
    - they won't be found when looked up via `BaseTreeNode` (and vice versa).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Instead of Document or Folder instances/models
        # always use associated BaseTreeNode instances/model
        if hasattr(self.instance, "basetreenode_ptr"):  # Document or Folder
            self.model = self.instance.basetreenode_ptr.__class__
            self.instance = self.instance.basetreenode_ptr


class NodeManager(models.Manager):
    pass


class NodeQuerySet(models.QuerySet):

    def delete(self, *args, **kwargs):
        deleted_item_ids = []
        for node in self:
            descendants = node.get_descendants()
            if len(descendants) > 0:
                for item in descendants:
                    if item.is_folder:
                        deleted_item_ids.append(str(item.pk))
                    else:
                        last_ver = item.document.versions.last()
                        for page in last_ver.pages.all():
                            deleted_item_ids.append(str(page.pk))
                    item.delete(*args, **kwargs)
            # At this point all descendants were deleted.
            # Self delete :)
            try:
                if node.is_folder:
                    deleted_item_ids.append(str(node.pk))
                else:
                    last_ver = node.document.versions.last()
                    for page in last_ver.pages.all():
                        deleted_item_ids.append(str(page.pk))
                node.delete(*args, **kwargs)
            except BaseTreeNode.DoesNotExist:
                # this node was deleted by earlier recursive call
                # it is ok, just skip
                pass

        self.publish_post_delete_task(deleted_item_ids)

    @if_redis_present
    def publish_post_delete_task(self, node_ids: List[str]):
        current_app.send_task(
            INDEX_REMOVE_NODE, kwargs={"item_ids": node_ids}, route_name="i3"
        )


CustomNodeManager = NodeManager.from_queryset(NodeQuerySet)


class BaseTreeNode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="children",
        verbose_name="parent",
    )
    # shortcut - helps to figure out if node is either folder or document
    # without performing extra joins. This field may be empty. In such
    # case you need to perform joins with Folder/Document table to figure
    # out what type of node is this instance.
    ctype = models.CharField(
        max_length=16,
        choices=(
            (NODE_TYPE_FOLDER, NODE_TYPE_FOLDER),
            (NODE_TYPE_DOCUMENT, NODE_TYPE_DOCUMENT),
        ),
        blank=True,
        null=True,
    )

    title = models.CharField(
        "Title", max_length=200, validators=[validators.safe_character_validator]
    )

    lang = models.CharField(
        "Language", max_length=8, blank=False, null=False, default="deu"
    )

    user = models.ForeignKey("User", related_name="nodes", on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    tags = TaggableManager(through=ColoredTag, manager=PolymorphicTagManager)

    # custom Manager + custom QuerySet
    objects = CustomNodeManager()

    @property
    def breadcrumb(self) -> List[Tuple[uuid.UUID, str]]:
        return [(item.id, item.title) for item in self.get_ancestors()]

    @property
    def idified_title(self):
        """
        Returns a title with ID part inserted at the end

        Example:
            input: title="My Invoices", id="233453"
            output: "My Invoices-233453"
        """

        return f"{self.title}-{self.id}"

    @property
    def _type(self) -> str:
        try:
            self.folder
        except Exception:
            return NODE_TYPE_DOCUMENT

        return NODE_TYPE_FOLDER

    @property
    def document_or_folder(self):
        """Returns instance of associated `Folder` or `Document` model"""
        return self.folder_or_document

    @property
    def folder_or_document(self):
        """Returns instance of associated `Folder` or `Document` model"""
        if self.is_folder:
            return self.folder

        return self.document

    @property
    def is_folder(self) -> bool:
        """Returns True if and only if this node is a folder"""
        if self.ctype in (NODE_TYPE_DOCUMENT, NODE_TYPE_FOLDER):
            return self.ctype == NODE_TYPE_FOLDER

        return self._type == NODE_TYPE_FOLDER

    @property
    def is_document(self) -> bool:
        """Returns True if and only if this node is a document"""
        if self.ctype in (NODE_TYPE_DOCUMENT, NODE_TYPE_FOLDER):
            return self.ctype == NODE_TYPE_DOCUMENT

        return self._type == NODE_TYPE_DOCUMENT

    def get_ancestors(self, include_self=True):
        """Returns all ancestors of the node"""
        sql = """
        WITH RECURSIVE tree AS (
            SELECT *, 0 as level FROM core_basetreenode WHERE id = %s
            UNION ALL
            SELECT core_basetreenode.*, level + 1
            FROM core_basetreenode, tree
            WHERE core_basetreenode.id = tree.parent_id
        )
        """
        node_id = uuid2raw_str(self.pk)
        if include_self:
            sql += "SELECT * FROM tree ORDER BY level DESC"
            return BaseTreeNode.objects.raw(sql, [node_id])

        sql += "SELECT * FROM tree WHERE NOT id = %s ORDER BY level DESC"

        return BaseTreeNode.objects.raw(sql, [node_id, node_id])

    def get_descendants(self, include_self=True):
        """Returns all descendants of the node"""
        sql = """
        WITH RECURSIVE tree AS (
            SELECT * FROM core_basetreenode WHERE id = %s
            UNION ALL
            SELECT core_basetreenode.* FROM core_basetreenode, tree
              WHERE core_basetreenode.parent_id = tree.id
        )
        """
        node_id = uuid2raw_str(self.pk)
        if include_self:
            sql += "SELECT * FROM tree"
            return BaseTreeNode.objects.raw(sql, [node_id])

        sql += "SELECT * FROM tree WHERE NOT id = %s"
        return BaseTreeNode.objects.raw(sql, [node_id, node_id])

    def save(self, *args, **kwargs):
        if not self.ctype:
            self.ctype = self.__class__.__name__.lower()

        super().save(*args, **kwargs)
        self.publish_post_save_task()

    @if_redis_present
    def publish_post_save_task(self):
        id_as_str = str(self.pk)
        current_app.send_task(
            INDEX_ADD_NODE, kwargs={"node_id": id_as_str}, route_name="i3"
        )

    def delete(self, *args, **kwargs):
        deleted_item_ids = []
        descendants = self.get_descendants(include_self=False)

        if len(descendants) > 0:
            for item in descendants:
                try:
                    if item.is_folder:
                        deleted_item_ids.append(str(item.pk))
                    else:
                        last_ver = item.document.versions.last()
                        for page in last_ver.pages.all():
                            deleted_item_ids.append(str(page.pk))

                    item.delete(*args, **kwargs)
                except BaseTreeNode.DoesNotExist:
                    pass
        # At this point all descendants were deleted.
        # Self delete :)
        try:
            if self.is_folder:
                deleted_item_ids.append(str(self.pk))
            else:
                last_ver = self.document.versions.last()
                for page in last_ver.pages.all():
                    deleted_item_ids.append(str(page.pk))
            super().delete(*args, **kwargs)
        except BaseTreeNode.DoesNotExist:
            # this node was deleted by earlier recursive call
            # it is ok, just skip
            pass

        self.publish_post_delete_task(deleted_item_ids)

    @if_redis_present
    def publish_post_delete_task(self, node_ids: List[str]):
        current_app.send_task(
            INDEX_REMOVE_NODE, kwargs={"item_ids": node_ids}, route_name="i3"
        )

    class Meta:
        # please do not confuse this "Documents" verbose name
        # with real Document object, which is derived from BaseNodeTree.
        # The reason for this naming confusing is that from the point
        # of view of users, the BaseNodeTree are just a list of documents.
        verbose_name = "Documents"
        verbose_name_plural = "Documents"
        _icon_name = "basetreenode"

        constraints = [
            models.UniqueConstraint(
                name="unique title per parent per user",
                fields=("parent", "title", "user_id"),
            ),
            # Prohibit `title` duplicates when `parent_id` is NULL
            models.UniqueConstraint(
                name="title_uniq_when_parent_is_null_per_user",
                fields=("title", "user_id"),
                condition=Q(parent__isnull=True),
            ),
        ]

    def __repr__(self):
        class_name = type(self).__name__
        return "{}({!r}, {!r})".format(class_name, self.pk, self.title)

    def __str__(self):
        class_name = type(self).__name__
        return "{}(pk={}, title='{}', ctype='{}')".format(
            class_name, self.pk, self.title, self.ctype
        )
