import Foundation

/// A task, and how it maps to its `Task` record in the CloudKit private database.
///
/// @REQ_REF(SW_APP_002) a title, an optional note, an optional due date and done — nothing else
/// @REQ_REF(IF_SYNC_001) one Task record per task, with the fields of the record schema
struct TaskItem: Identifiable, Equatable {
    enum Field: String, CaseIterable { case title, note, due, done, order }

    let id: UUID
    var title: String
    var note: String?
    var due: Date?
    var isDone = false
    var order: Double
    /// When each field last changed, so a merge can keep the later value per field.
    var stamps: [Field: Date] = [:]

    func record() -> [String: Any] {
        var fields: [String: Any] = ["id": id.uuidString, "title": title,
                                     "done": isDone ? 1 : 0, "order": order]
        fields["note"] = note
        fields["due"] = due
        return fields
    }
}
