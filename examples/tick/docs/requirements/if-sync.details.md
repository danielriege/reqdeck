## IF_SYNC_001

| Field | Type | Notes |
|---|---|---|
| `id` | String | UUID, the record name |
| `title` | String | Never empty |
| `note` | String | Absent when there is none |
| `due` | Date | Absent when there is none |
| `done` | Int64 | `0` open, `1` done |
| `list` | Reference | The `TaskList` record, deleting the task with it |
| `order` | Double | Manual position within the list — SW_APP_004 |
| `stamps` | Bytes | Per-field modification times — IF_SYNC_003 |

## IF_SYNC_002

| Field | Type | Notes |
|---|---|---|
| `id` | String | UUID, the record name |
| `name` | String | Never empty |
| `isInbox` | Int64 | `1` on exactly one list per account — SW_APP_003 |
