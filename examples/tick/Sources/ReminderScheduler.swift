import Foundation
import UserNotifications

/// Keeps one pending local notification per open task with a due date.
///
/// @REQ_REF(SW_APP_005) exactly one pending notification for each open task with a due date
/// @REQ_REF(SW_APP_006) snooze to 10 minutes, to 1 hour, or to 09:00 tomorrow
struct ReminderScheduler {
    enum Snooze { case tenMinutes, oneHour, tomorrowMorning }

    let center: UNUserNotificationCenter
    var calendar = Calendar.current

    func sync(_ tasks: [TaskItem]) {
        let due = tasks.filter { !$0.isDone && $0.due != nil }
        center.removeAllPendingNotificationRequests()
        for task in due {
            let parts = calendar.dateComponents([.year, .month, .day, .hour, .minute], from: task.due!)
            let content = UNMutableNotificationContent()
            content.title = task.title
            let trigger = UNCalendarNotificationTrigger(dateMatching: parts, repeats: false)
            center.add(UNNotificationRequest(identifier: task.id.uuidString, content: content, trigger: trigger))
        }
    }

    func snoozed(_ snooze: Snooze, from now: Date) -> Date {
        switch snooze {
        case .tenMinutes: return now.addingTimeInterval(10 * 60)
        case .oneHour: return now.addingTimeInterval(60 * 60)
        case .tomorrowMorning:
            let tomorrow = calendar.date(byAdding: .day, value: 1, to: now)!
            return calendar.date(bySettingHour: 9, minute: 0, second: 0, of: tomorrow)!
        }
    }
}
