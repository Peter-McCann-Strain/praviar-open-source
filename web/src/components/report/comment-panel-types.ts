export interface CommentPanelComment {
  id: string;
  user_id: string;
  body: string;
  target_type: string;
  target_id: string;
  parent_id: string | null;
  resolved: boolean;
  resolved_by?: string | null;
  resolved_at?: string | null;
  assigned_to?: string | null;
  assigned_by?: string | null;
  assigned_reviewer_name?: string | null;
  assigned_reviewer_email?: string | null;
  assigned_at?: string | null;
  assignment_event_count?: number;
  last_assignment_at?: string | null;
  queue_age_hours?: number | null;
  is_overdue?: boolean;
  escalation_status?: string | null;
  escalated_by?: string | null;
  escalated_by_name?: string | null;
  escalated_by_email?: string | null;
  escalated_at?: string | null;
  escalation_event_count?: number;
  last_escalation_at?: string | null;
  escalated_to_review?: boolean;
  review_handoff_comment_id?: string | null;
  created_at: string;
}

export interface CommentPanelReviewer {
  id: string;
  label: string;
  email?: string;
  role?: string;
}

export interface CommentAssignmentHistoryEvent {
  id: string;
  comment_id: string;
  analysis_id: string;
  event_type: string;
  assigned_to?: string | null;
  assigned_to_name?: string | null;
  assigned_to_email?: string | null;
  assigned_by?: string | null;
  assigned_by_name?: string | null;
  assigned_by_email?: string | null;
  created_at: string;
}

export interface CommentAssignmentHistory {
  comment_id: string;
  thread_root_comment_id: string;
  analysis_id: string;
  assignment_event_count: number;
  last_assignment_at?: string | null;
  events: CommentAssignmentHistoryEvent[];
}
