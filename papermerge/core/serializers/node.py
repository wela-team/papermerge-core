from rest_framework_json_api import serializers
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework import serializers as rest_serializers

from papermerge.core.models import (
    BaseTreeNode,
    Folder
)
from papermerge.core.serializers import (
    FolderSerializer,
    DocumentSerializer
)


ALL = 'all'
ONLY_ORIGINAL = 'only_original'
ONLY_LAST = 'only_last'
ONLY_ORIGINAL_AND_LAST = 'only_original_and_last'
ZIP = 'zip'
TARGZ = 'targz'


class NodeSerializer(serializers.PolymorphicModelSerializer):
    polymorphic_serializers = [
        FolderSerializer,
        DocumentSerializer
    ]

    parent = ResourceRelatedField(queryset=Folder.objects)

    class Meta:
        model = BaseTreeNode
        resource_name = 'nodes'
        fields = (
            'id',
            'title',
            'parent',
            'created_at',
            'updated_at',
        )


class NodeIDSerializer(rest_serializers.Serializer):
    id = rest_serializers.CharField(max_length=32)


class NodeMoveSerializer(rest_serializers.Serializer):
    # Original nodes parent
    source_parent = NodeIDSerializer(required=True)
    # new parent i.e. target folder
    target_parent = NodeIDSerializer(required=True)
    # nodes to move under the new parent
    nodes = NodeIDSerializer(many=True)


class NodesDownloadSerializer(rest_serializers.Serializer):
    # list of nodes to download
    node_ids = rest_serializers.ListField(
        child=rest_serializers.CharField()
    )
    file_name = rest_serializers.CharField(
        max_length=32,
        required=False
    )
    # What to include in downloaded file?
    include_version = rest_serializers.ChoiceField(
        choices=(
            (ALL, 'All'),
            (ONLY_ORIGINAL, 'Only original'),
            (ONLY_LAST, 'Only last'),
            (ONLY_ORIGINAL_AND_LAST, 'Only original and last')
        ),
        default=ONLY_LAST
    )
    archive_type = rest_serializers.ChoiceField(
        choices=(
            (TARGZ, '.tar.gz'),
            (ZIP, '.zip')
        ),
        default=ZIP
    )
