import {LoaderFunctionArgs} from "react-router"

import DualPanel from "@/components/DualPanel"
import {fetchPaginatedNodes, setCurrentNode} from "@/slices/dualPanel"

import {getCurrentUser} from "@/utils"
import {store} from "@/app/store"

import type {User} from "@/types"
import {INITIAL_PAGE_SIZE} from "@/cconstants"

export default function Home() {
  return <DualPanel />
}

export async function loader({params, request}: LoaderFunctionArgs) {
  const url = new URL(request.url)
  const user: User = await getCurrentUser()
  let folderId
  const state = store.getState()
  const pageSize = state.dualPanel.mainPanel.commander?.lastPageSize
  const urlParams = new URLSearchParams(
    `page_number=1&page_size=${pageSize || INITIAL_PAGE_SIZE}`
  )

  if (params.folderId) {
    folderId = params.folderId
  } else {
    folderId = user.inbox_folder_id
  }

  store.dispatch(
    setCurrentNode({
      node: {id: folderId, ctype: "folder", breadcrumb: null},
      panel: "main"
    })
  )

  await store.dispatch(
    fetchPaginatedNodes({folderId, panel: "main", urlParams: urlParams})
  )

  return {folderId, urlParams: url.searchParams}
}
