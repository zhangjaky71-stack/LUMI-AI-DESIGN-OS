DROP INDEX IF EXISTS ix_comment_revisions_comment;

-- statement-breakpoint

DROP TABLE IF EXISTS comment_revisions;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_comments_thread_created;

-- statement-breakpoint

DROP TABLE IF EXISTS comments;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_comment_threads_artifact;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_comment_threads_version;

-- statement-breakpoint

DROP TABLE IF EXISTS comment_threads;
