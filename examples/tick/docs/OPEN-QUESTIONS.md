# Open Questions

Everything not yet decided. One question per `###` heading, fields on single lines.

```
### <ID> — <short title>
**Question:** <what has to be decided>
**Answer:** <blank until decided>
**Blocks:** <what is waiting on it, or —>
```

IDs are `OQ-TTNN` — `TT` is the topic number, `NN` the question within it. **Questions never
move.** When one is answered, fill in `Answer:` and leave it where it is.

---

## Topic 01 — Scope and users

### OQ-0101 — Who is it for
**Question:** Individuals keeping their own lists, households sharing lists, or both from the start?
**Answer:** **Individuals first.** Chosen 2026-09-02. Shared lists are the most requested feature in every to-do app's reviews, but they need CloudKit sharing, invitations and a conflict model for two people — OQ-0403 — and none of that is needed to prove the app is worth using. The household stories stay, marked future.
**Blocks:** Everything traces to the stories

### OQ-0102 — Which devices
**Question:** iPhone only, or iPad and Mac as well?
**Answer:** **iPhone and iPad, one universal app.** Chosen 2026-09-02. SwiftUI makes the iPad layout nearly free; a Mac app is a different interaction model and waits.
**Blocks:** Sync — topic 04

## Topic 02 — Lists and tasks

### OQ-0201 — What a task is
**Question:** Which fields does a task have?
**Answer:** **A title, an optional note, an optional due date, and done.** Chosen 2026-09-04. Nothing else in v1: priorities and tags are where to-do apps go to die, and every field added is a field the quick-capture path has to step around. A task can be added with a title alone.
**Blocks:** SYS_001, the record schema

### OQ-0202 — How many lists
**Question:** One list, a fixed set, or as many as the user wants?
**Answer:** **As many as the user wants, plus one Inbox that always exists.** Chosen 2026-09-04. Quick capture needs somewhere to put a task without asking which list; the Inbox is that place, so it can be neither deleted nor renamed.
**Blocks:** SYS_002

### OQ-0203 — Ordering
**Question:** How are tasks ordered within a list?
**Answer:** **By hand, with done tasks after the open ones.** Chosen 2026-09-05. Sorting by due date is a view, not an order — the user's own order is what is stored.
**Blocks:** SW_APP_004

### OQ-0204 — Undoing a deletion
**Question:** Is a deleted task recoverable — an undo toast, a "recently deleted" list, or neither?
**Answer:**
**Blocks:** Delete behaviour in the app

## Topic 03 — Reminders

### OQ-0301 — When to remind
**Question:** When does a reminder fire, and what can the user do with it?
**Answer:** **At the due time, once, with three snooze options: 10 minutes, 1 hour, or 09:00 tomorrow.** Chosen 2026-09-08. Local notifications only — no push server — so a reminder works offline and costs nothing to run.
**Blocks:** SYS_003, SYS_004

### OQ-0302 — Recurring tasks
**Question:** Do tasks repeat — daily, weekly, "every second Tuesday"?
**Answer:**
**Blocks:** The task fields, reminder scheduling

## Topic 04 — Sync and storage

### OQ-0401 — Where the data lives
**Question:** Own server, a third-party backend, or the user's iCloud?
**Answer:** **On the device, synced through the user's CloudKit private database. No server of our own.** Chosen 2026-09-10. Nothing to run, nothing to breach, and the user's data never reaches us. A change reaches the user's other devices within 30 seconds when both are online — CloudKit's push delivery makes that routine, and slower would feel broken when an iPad sits beside the phone. The app works fully offline and syncs once a connection returns.
**Blocks:** SYS_005, SYS_006, the record schema

### OQ-0402 — Conflicting edits
**Question:** Two devices edit the same task while offline. Which edit wins?
**Answer:** **The later edit wins, field by field.** Chosen 2026-09-11, revised 2026-10-02. Whole-record last-writer-wins was the first answer; it loses a title edit on the phone when the iPad ticks the same task off. Per-field timestamps keep both.
**Blocks:** SYS_009, IF_SYNC_003

### OQ-0403 — Sharing a list
**Question:** How does a list get shared with another person — CloudKit sharing, a link, an invitation in the app?
**Answer:**
**Blocks:** B-01, B-02

## Topic 05 — Widget

### OQ-0501 — What the widget shows
**Question:** Which widget sizes, showing what?
**Answer:** **Small: how many open tasks are due today. Medium: the next three open tasks by due date.** Chosen 2026-09-15. The large size adds nothing the medium does not, minus a glance.
**Blocks:** SYS_007

### OQ-0502 — Ticking off from the widget
**Question:** Can a task be ticked off from the widget, or does a tap open the app?
**Answer:** **Ticked off in place,** with an App Intent. Chosen 2026-09-15. iOS 17 widgets are interactive, and opening the app to tick one box is the friction the widget exists to remove.
**Blocks:** SW_WID_003

## Topic 06 — Privacy

### OQ-0601 — Analytics and crash reporting
**Question:** Which analytics or crash-reporting SDKs does the app ship with?
**Answer:** **None.** Chosen 2026-09-02. Apple's own crash reports, which the user opts into, are enough for an app this size, and a privacy label reading "Data Not Collected" is a feature.
**Blocks:** SYS_008
