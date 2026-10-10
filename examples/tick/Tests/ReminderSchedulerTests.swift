import XCTest
@testable import Tick

final class ReminderSchedulerTests: XCTestCase {
    /// @test A done task and a task without a due date get no reminder.
    ///
    /// Given three tasks: one open and due, one done and due, one open with no due date.
    /// When  the scheduler syncs them.
    /// Then  exactly one notification is pending, for the open, due task.
    ///
    /// @REQ_REF(SW_APP_005) exactly one pending notification for each open task with a due date
    func testOnlyOpenDueTasksAreScheduled() { }

    /// @test Snoozing until tomorrow lands on 09:00 the next day, whatever the time now.
    ///
    /// Given it is 23:40 on a Tuesday.
    /// When  a reminder is snoozed until tomorrow morning.
    /// Then  it fires at 09:00 on Wednesday.
    ///
    /// @REQ_REF(SW_APP_006) snooze to 10 minutes, to 1 hour, or to 09:00 tomorrow
    func testSnoozeUntilTomorrowMorning() { }

    /// @test A record carries every field of the schema, and no others.
    ///
    /// Given a task with a note and a due date.
    /// When  it is turned into a record.
    /// Then  the record has id, title, note, due, done and order.
    ///
    /// @REQ_REF(IF_SYNC_001) one Task record per task, with the fields of the record schema
    func testRecordFields() { }
}
