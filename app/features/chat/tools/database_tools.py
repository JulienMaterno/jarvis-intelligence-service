"""
Database Tools for Chat.

This module contains tools for database queries, writes, schema management,
and backup operations.
"""

import re
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from app.core.database import supabase
from .base import WRITABLE_TABLES, READONLY_TABLES, SYNC_MANAGED_TABLES, logger


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

DATABASE_TOOLS = [
    {
        "name": "execute_sql_write",
        "description": """Execute a write SQL statement (UPDATE, INSERT, DELETE) against the database.

REQUIRES USER CONFIRMATION - Always set user_confirmed=false first to show what will change, then call again with user_confirmed=true after user confirms.

WHEN TO USE:
- User says "update X to Y", "change X", "set X to Y", "fix X"
- Modifying single fields that specific tools don't handle
- Bulk updates (with user confirmation)
- Any direct data manipulation request

HOW TO USE (2-step process):
1. FIRST CALL: Set user_confirmed=false to preview the change
2. SECOND CALL: After user confirms, call with user_confirmed=true

SQL FORMAT REQUIREMENTS:
- UPDATE: UPDATE table SET col1='val1', col2='val2' WHERE id='uuid'
- INSERT: INSERT INTO table (col1, col2) VALUES ('val1', 'val2')
- DELETE: DELETE FROM table WHERE id='uuid'
- MUST include WHERE id='uuid' for UPDATE/DELETE (safety requirement)

IMPORTANT BEHAVIORS:
- The tool automatically sets updated_at=now() on updates
- The tool automatically sets last_sync_source='supabase' for sync-managed tables (this triggers sync to Notion)
- Use .select() is handled internally - you'll get the updated record back

EXAMPLE - Update application status:
sql: "UPDATE applications SET status='Applied' WHERE id='550e8400-e29b-41d4-a716-446655440000'"
description: "Mark Cosmos application as Applied"
user_confirmed: false (first), then true (after confirmation)

WRITABLE TABLES:
- contacts, meetings, tasks, journals, reflections
- applications, linkedin_posts, books, highlights

READ-ONLY TABLES (managed by sync - cannot modify):
- calendar_events, emails, beeper_chats, beeper_messages, transcripts

For common operations, prefer specific tools when available:
- Tasks: create_task, complete_task, update_task
- Contacts: create_contact, update_contact
- Meetings/Reflections: create_meeting, create_reflection""",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The SQL statement. Format: UPDATE table SET col='val' WHERE id='uuid'"
                },
                "user_confirmed": {
                    "type": "boolean",
                    "description": "Set false first to preview, then true after user confirms"
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of what this change does"
                }
            },
            "required": ["sql", "user_confirmed", "description"]
        }
    },
    {
        "name": "update_record",
        "description": """Update a single record in the database using structured JSON input.

USE THIS INSTEAD OF execute_sql_write when updating content with special characters (commas, quotes, etc.)

WHEN TO USE:
- Updating text content (descriptions, notes, email content)
- Any field that might contain commas, quotes, or special characters
- Single record updates by ID

WRITABLE TABLES:
- contacts, meetings, tasks, journals, reflections
- applications, linkedin_posts, books, highlights

EXAMPLE - Update reflection content:
table: "reflections"
record_id: "419ac9a1-29f9-440e-9962-ef86bc8cd4bb"
updates: {"content": "Full email content here with commas, quotes, etc."}
user_confirmed: false (first call), then true (after confirmation)""",
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": "Table name (e.g., 'reflections', 'meetings', 'tasks')"
                },
                "record_id": {
                    "type": "string",
                    "description": "UUID of the record to update"
                },
                "updates": {
                    "type": "object",
                    "description": "Key-value pairs of fields to update. Can contain any text content."
                },
                "user_confirmed": {
                    "type": "boolean",
                    "description": "Set false first to preview, then true after user confirms"
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of what this change does"
                }
            },
            "required": ["table", "record_id", "updates", "user_confirmed"]
        }
    },
    {
        "name": "query_database",
        "description": """Execute a read-only SQL query against the knowledge database.
Use this for novel/complex queries that specific tools can't handle. For common operations, prefer specific tools like get_applications, search_contacts, get_tasks.

FULL DATABASE SCHEMA:
====================

CORE DATA:
----------
- contacts: CRM contacts (id, first_name, last_name, email, company, job_title, phone, birthday, linkedin_url, location, notes, dynamic_properties, deleted_at, created_at, updated_at)
- meetings: Meeting records (id, title, date, location, summary, contact_id, contact_name, topics_discussed, people_mentioned, action_items, source_file, source_transcript_id)
- tasks: Action items (id, title, description, status, priority, due_date, completed_at, project, tags, origin_id, origin_type)
- reflections: Personal reflections/notes (id, title, topic_key, content, tags, date, mood, energy_level, people_mentioned, source_file, source_transcript_id, deleted_at)
- journals: Daily journal entries (id, date, title, content, mood, energy, gratitude, wins, challenges, tomorrow_focus)

CALENDAR & EMAIL:
-----------------
- calendar_events: Google Calendar (id, google_event_id, calendar_id, summary, description, start_time, end_time, location, status, attendees, contact_id)
- emails: Gmail messages (id, google_message_id, thread_id, subject, sender, recipient, date, snippet, body_text, body_html, labels, is_read, contact_id)

MEDIA & CONTENT:
----------------
- transcripts: Voice memo transcriptions (id, full_text, source_file, audio_duration_seconds, language, segments, speakers, model_used)
- documents: Personal documents (id, title, type, content, tags, notion_page_id, deleted_at)
- books: Reading list (id, title, author, status, rating, current_page, total_pages, summary, notes)
- highlights: Book highlights (id, book_id, book_title, content, note, chapter, page_number, is_favorite)

APPLICATIONS & LINKEDIN:
------------------------
- applications: Grant/fellowship applications (id, name, application_type, status, institution, website, grant_amount, deadline, context, notes, content)
- linkedin_posts: LinkedIn content (id, title, post_date, status, pillar, likes, content)

MESSAGING (Beeper):
-------------------
- beeper_chats: Chat rooms/DMs (id, beeper_chat_id, platform, chat_type, chat_name, contact_id, needs_response, is_archived)
- beeper_messages: Chat messages (id, beeper_event_id, beeper_chat_id, content, is_outgoing, timestamp, contact_id)

SQL TIPS:
---------
- Use ILIKE for case-insensitive search: WHERE title ILIKE '%keyword%'
- Filter active contacts: WHERE deleted_at IS NULL
- Join contacts: JOIN contacts c ON meetings.contact_id = c.id
- Date ranges: WHERE date >= '2025-01-01' AND date < '2025-02-01'
- JSON array search: WHERE 'tag' = ANY(tags)
- Default limit is 100, max is 1000: LIMIT 500
- ALWAYS fetch ALL records when user asks for a list!
- Include 'id' column for any records you might need to update

IMPORTANT: Only SELECT queries allowed. Use specific tools when available.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "The SELECT SQL query to execute"
                }
            },
            "required": ["sql"]
        }
    },
    {
        "name": "list_database_tables",
        "description": """List all tables and their columns in the database.
Use when user asks about database structure or available data.""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "create_database_table",
        "description": """Create a new table in the database. REQUIRES user_confirmed=true.
Use when user explicitly asks to create a new table for storing custom data.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Table name (lowercase, underscores allowed)"
                },
                "columns": {
                    "type": "array",
                    "description": "Column definitions",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string", "description": "PostgreSQL type: TEXT, INTEGER, BOOLEAN, TIMESTAMPTZ, UUID, JSONB"},
                            "nullable": {"type": "boolean", "default": True},
                            "default": {"type": "string"},
                            "unique": {"type": "boolean"}
                        },
                        "required": ["name", "type"]
                    }
                },
                "user_confirmed": {
                    "type": "boolean",
                    "description": "Must be true to execute"
                }
            },
            "required": ["table_name", "columns", "user_confirmed"]
        }
    },
    {
        "name": "add_column_to_table",
        "description": """Add a column to an existing table. REQUIRES user_confirmed=true.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "column_name": {"type": "string"},
                "column_type": {"type": "string", "description": "PostgreSQL type"},
                "nullable": {"type": "boolean", "default": True},
                "default_value": {"type": "string"},
                "user_confirmed": {"type": "boolean"}
            },
            "required": ["table_name", "column_name", "column_type", "user_confirmed"]
        }
    },
    {
        "name": "update_data_batch",
        "description": """Update multiple records in a single operation with verification.
REQUIRES user_confirmed=true. Use for bulk updates by ID.

WRITABLE TABLES: contacts, meetings, tasks, journals, reflections, applications, linkedin_posts, books, highlights""",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Target table name"
                },
                "updates": {
                    "type": "array",
                    "description": "Array of update objects. Each MUST have 'id' plus fields to update.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Record UUID (required)"}
                        },
                        "required": ["id"]
                    }
                },
                "user_confirmed": {
                    "type": "boolean",
                    "description": "Set false first to preview, then true after user confirms ALL updates"
                }
            },
            "required": ["table_name", "updates", "user_confirmed"]
        }
    },
    {
        "name": "insert_data_batch",
        "description": """Insert multiple rows into a table. Use for bulk data insertion.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "rows": {
                    "type": "array",
                    "description": "Array of row objects to insert",
                    "items": {"type": "object"}
                }
            },
            "required": ["table_name", "rows"]
        }
    },
    {
        "name": "get_database_backup_status",
        "description": """Check the database backup status and recent backups.
Use when user asks about data safety or before making significant changes.""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "backup_table",
        "description": """Create a backup of a specific table to storage.
Use before making destructive changes or when user wants to snapshot data.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Table to backup"
                }
            },
            "required": ["table_name"]
        }
    },
]


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def _execute_sql_write(input: Dict) -> Dict[str, Any]:
    """Execute a write SQL statement with confirmation requirement."""
    sql = input.get("sql", "").strip()
    user_confirmed = input.get("user_confirmed", False)
    description = input.get("description", "")

    if not sql:
        return {"error": "SQL statement is required"}

    sql_upper = sql.upper()

    # Determine operation type
    if sql_upper.startswith("UPDATE"):
        operation = "UPDATE"
    elif sql_upper.startswith("INSERT"):
        operation = "INSERT"
    elif sql_upper.startswith("DELETE"):
        operation = "DELETE"
    else:
        return {"error": "Only UPDATE, INSERT, or DELETE statements are allowed. For SELECT, use query_database."}

    # Block multi-statement injection via semicolons
    # Strip trailing semicolons first, then check for embedded ones
    sql_stripped = sql.rstrip().rstrip(";").strip()
    if ";" in sql_stripped:
        return {"error": "Multiple SQL statements (semicolons) are not allowed. Submit one statement at a time."}

    # Block extremely dangerous SQL commands (using word boundaries to avoid false positives)
    dangerous_patterns = [
        r'\bDROP\s+(TABLE|DATABASE|INDEX|VIEW)',
        r'\bTRUNCATE\s+',
        r'\bALTER\s+(TABLE|DATABASE)',
        r'^\s*GRANT\s+',
        r'^\s*REVOKE\s+',
        r'\bCREATE\s+(TABLE|DATABASE|INDEX|VIEW|USER)',
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, sql_upper):
            return {"error": f"Query contains forbidden SQL command pattern: {pattern}"}

    # Extract table name
    if operation == "UPDATE":
        table_match = re.search(r'UPDATE\s+(\w+)', sql, re.IGNORECASE)
    elif operation == "INSERT":
        table_match = re.search(r'INTO\s+(\w+)', sql, re.IGNORECASE)
    else:  # DELETE
        table_match = re.search(r'FROM\s+(\w+)', sql, re.IGNORECASE)

    if not table_match:
        return {"error": "Could not parse table name from query"}

    table_name = table_match.group(1).lower()

    if table_name not in WRITABLE_TABLES:
        if table_name in READONLY_TABLES:
            return {
                "error": f"Table '{table_name}' is read-only (sync-managed). Cannot modify.",
                "writable_tables": WRITABLE_TABLES
            }
        return {"error": f"Table '{table_name}' is not in the allowed writable tables list."}

    # For UPDATE/DELETE, require WHERE clause with specific ID
    if operation in ("UPDATE", "DELETE"):
        if "WHERE" not in sql_upper:
            return {"error": f"{operation} requires a WHERE clause for safety. Include WHERE id='uuid'"}

        # Check for broad conditions (no specific ID)
        where_match = re.search(r'WHERE\s+(.+?)(?:$|;)', sql, re.IGNORECASE | re.DOTALL)
        if where_match:
            where_clause = where_match.group(1).upper()
            # Must have id = 'uuid' pattern
            if not re.search(r"\w*id\s*=\s*'[A-F0-9a-f\-]+'", where_clause, re.IGNORECASE):
                return {
                    "error": f"{operation} must target specific record(s) by id. Got WHERE: {where_match.group(1)[:50]}",
                    "hint": "Use WHERE id='specific-uuid' to target a specific record"
                }

    # If not confirmed, return preview
    if not user_confirmed:
        # Try to get affected records for preview
        preview_data = None
        affected_count = "unknown"

        if operation == "UPDATE" or operation == "DELETE":
            where_match = re.search(r'WHERE\s+(.+?)(?:$|;)', sql, re.IGNORECASE | re.DOTALL)
            if where_match:
                where_clause = where_match.group(1)
                try:
                    preview_sql = f"SELECT * FROM {table_name} WHERE {where_clause} LIMIT 5"
                    preview_result = supabase.rpc("exec_sql", {"query": preview_sql}).execute()
                    if preview_result.data:
                        preview_data = preview_result.data
                        affected_count = len(preview_result.data)
                except Exception:
                    pass

        return {
            "status": "CONFIRMATION_REQUIRED",
            "operation": operation,
            "table": table_name,
            "description": description,
            "sql_preview": sql[:500],
            "affected_records": affected_count,
            "preview_data": preview_data,
            "message": f"Ready to {operation} on '{table_name}'. Please confirm you want to proceed.",
            "instructions": "Ask the user to confirm, then call execute_sql_write again with user_confirmed=true"
        }

    # Execute the SQL
    try:
        # For tables managed by sync, add updated_at and last_sync_source
        if operation == "UPDATE" and table_name in SYNC_MANAGED_TABLES:
            # Add updated_at if not present
            if "updated_at" not in sql.lower():
                sql = re.sub(
                    r'\bSET\s+',
                    f"SET updated_at='{datetime.now(timezone.utc).isoformat()}', ",
                    sql,
                    count=1,
                    flags=re.IGNORECASE
                )
            # Add last_sync_source
            if "last_sync_source" not in sql.lower():
                sql = re.sub(
                    r'\bSET\s+',
                    "SET last_sync_source='supabase', ",
                    sql,
                    count=1,
                    flags=re.IGNORECASE
                )

        # Execute using RPC
        result = supabase.rpc("exec_sql", {"query": sql}).execute()

        # For UPDATE, try to get the updated record
        updated_record = None
        if operation == "UPDATE":
            where_match = re.search(r'WHERE\s+(.+?)(?:$|;)', sql, re.IGNORECASE | re.DOTALL)
            if where_match:
                where_clause = where_match.group(1)
                try:
                    verify_sql = f"SELECT * FROM {table_name} WHERE {where_clause} LIMIT 1"
                    verify_result = supabase.rpc("exec_sql", {"query": verify_sql}).execute()
                    if verify_result.data:
                        updated_record = verify_result.data[0]
                except Exception:
                    pass

        logger.info(f"SQL write executed: {operation} on {table_name}")

        return {
            "status": "success",
            "operation": operation,
            "table": table_name,
            "description": description,
            "updated_record": updated_record,
            "message": f"Successfully executed {operation} on '{table_name}'"
        }

    except Exception as e:
        logger.error(f"SQL write failed: {e}")
        return {"error": f"SQL execution failed: {str(e)}"}


def _update_record(input: Dict) -> Dict[str, Any]:
    """Update a single record using structured JSON input."""
    table = input.get("table", "").strip().lower()
    record_id = input.get("record_id", "").strip()
    updates = input.get("updates", {})
    user_confirmed = input.get("user_confirmed", False)
    description = input.get("description", "")

    if not table:
        return {"error": "table is required"}
    if not record_id:
        return {"error": "record_id is required"}
    if not updates:
        return {"error": "updates object is required and must not be empty"}

    if table not in WRITABLE_TABLES:
        if table in READONLY_TABLES:
            return {"error": f"Table '{table}' is read-only (sync-managed). Cannot modify."}
        return {"error": f"Table '{table}' is not in the allowed writable tables list."}

    # Get current record for preview
    try:
        current = supabase.table(table).select("*").eq("id", record_id).execute()
        if not current.data:
            return {"error": f"Record not found: {record_id}"}
        current_record = current.data[0]
    except Exception as e:
        return {"error": f"Failed to fetch current record: {str(e)}"}

    if not user_confirmed:
        # Build preview of changes
        changes_preview = {}
        for key, new_value in updates.items():
            old_value = current_record.get(key)
            if isinstance(new_value, str) and len(new_value) > 200:
                new_value_preview = new_value[:200] + "..."
            else:
                new_value_preview = new_value
            if isinstance(old_value, str) and len(str(old_value)) > 200:
                old_value_preview = str(old_value)[:200] + "..."
            else:
                old_value_preview = old_value
            changes_preview[key] = {"old": old_value_preview, "new": new_value_preview}

        return {
            "status": "CONFIRMATION_REQUIRED",
            "table": table,
            "record_id": record_id,
            "description": description,
            "changes_preview": changes_preview,
            "message": f"Ready to update record in '{table}'. Please confirm.",
            "instructions": "Ask the user to confirm, then call update_record again with user_confirmed=true"
        }

    # Execute the update
    try:
        # Add metadata
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        if table in SYNC_MANAGED_TABLES:
            updates["last_sync_source"] = "supabase"

        supabase.table(table).update(updates).eq("id", record_id).execute()

        # Verify update
        verify = supabase.table(table).select("*").eq("id", record_id).execute()
        updated_record = verify.data[0] if verify.data else None

        logger.info(f"Record updated: {table}/{record_id}")

        return {
            "status": "success",
            "table": table,
            "record_id": record_id,
            "fields_updated": list(updates.keys()),
            "updated_record": updated_record,
            "message": f"Successfully updated record in '{table}'"
        }

    except Exception as e:
        logger.error(f"Record update failed: {e}")
        return {"error": f"Update failed: {str(e)}"}


def _query_database(sql: str) -> Dict[str, Any]:
    """Execute a read-only SQL query."""
    if not sql:
        return {"error": "SQL query is required"}

    sql_upper = sql.strip().upper()

    # Only allow SELECT queries
    if not sql_upper.startswith("SELECT"):
        return {"error": "Only SELECT queries are allowed. For writes, use execute_sql_write or specific tools."}

    # Block multi-statement injection via semicolons
    sql_no_trailing = sql.strip().rstrip(";").strip()
    if ";" in sql_no_trailing:
        return {"error": "Multiple SQL statements (semicolons) are not allowed. Submit one SELECT statement."}

    # Block dangerous operations even in SELECT
    # Strip quoted strings before checking to avoid false positives on words inside string literals
    sql_without_strings = re.sub(r"'[^']*'", "''", sql_upper)
    dangerous_patterns = [
        r'\bDROP\b', r'\bDELETE\b', r'\bUPDATE\b', r'\bINSERT\b',
        r'\bTRUNCATE\b', r'\bALTER\b', r'\bCREATE\b', r'\bGRANT\b', r'\bREVOKE\b'
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, sql_without_strings):
            return {"error": f"Query contains forbidden operation: {pattern}"}

    # Add default LIMIT if not present
    if "LIMIT" not in sql_upper:
        sql = sql.rstrip(";") + " LIMIT 100"
    else:
        # Enforce max limit of 1000
        limit_match = re.search(r'LIMIT\s+(\d+)', sql_upper)
        if limit_match and int(limit_match.group(1)) > 1000:
            sql = re.sub(r'LIMIT\s+\d+', 'LIMIT 1000', sql, flags=re.IGNORECASE)

    try:
        result = supabase.rpc("exec_sql", {"query": sql}).execute()

        rows = result.data if result.data else []
        return {
            "count": len(rows),
            "data": rows,
            "query": sql[:200] + "..." if len(sql) > 200 else sql
        }
    except Exception as e:
        logger.error(f"Query failed: {e}")
        return {"error": f"Query failed: {str(e)}"}


def _list_database_tables(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """List all tables and their columns in the database."""
    try:
        known_tables = [
            "contacts", "meetings", "tasks", "journals", "reflections",
            "calendar_events", "emails", "transcripts", "books", "highlights",
            "applications", "linkedin_posts", "beeper_chats", "beeper_messages",
            "sync_logs", "sync_state", "chat_messages", "scheduled_briefings"
        ]

        tables_info = []
        for table_name in known_tables:
            try:
                result = supabase.table(table_name).select("*").limit(1).execute()
                if result.data:
                    columns = list(result.data[0].keys())
                else:
                    columns = ["(table exists, no sample data)"]
                tables_info.append({
                    "table": table_name,
                    "columns": columns,
                    "status": "accessible"
                })
            except Exception as e:
                if "does not exist" not in str(e).lower():
                    tables_info.append({
                        "table": table_name,
                        "columns": [],
                        "status": f"error: {str(e)[:50]}"
                    })

        return {
            "status": "success",
            "tables": tables_info,
            "total_tables": len(tables_info),
            "note": "Use query_database for detailed column types"
        }
    except Exception as e:
        logger.error(f"Failed to list tables: {e}")
        return {"error": str(e)}


def _create_database_table(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new table in the database."""
    try:
        table_name = tool_input.get("table_name", "").lower().strip()
        columns = tool_input.get("columns", [])
        user_confirmed = tool_input.get("user_confirmed", False)

        if not table_name:
            return {"error": "table_name is required"}

        if not columns:
            return {"error": "columns list is required"}

        # Validate table name
        if not re.match(r'^[a-z][a-z0-9_]*$', table_name):
            return {"error": "Table name must start with letter, contain only lowercase letters, numbers, underscores"}

        # Don't allow overwriting system tables
        protected_tables = [
            "contacts", "meetings", "tasks", "journals", "reflections",
            "calendar_events", "emails", "transcripts", "sync_logs"
        ]
        if table_name in protected_tables:
            return {"error": f"Cannot create table '{table_name}' - it's a protected system table"}

        if not user_confirmed:
            column_defs = []
            for col in columns:
                col_def = f"  {col['name']} {col['type'].upper()}"
                if not col.get("nullable", True):
                    col_def += " NOT NULL"
                if col.get("default"):
                    col_def += f" DEFAULT {col['default']}"
                if col.get("unique"):
                    col_def += " UNIQUE"
                column_defs.append(col_def)

            preview_sql = f"""CREATE TABLE {table_name} (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
{chr(10).join(column_defs)},
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);"""
            return {
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Ready to create table '{table_name}'. Please confirm.",
                "preview_sql": preview_sql,
                "columns": columns,
                "instructions": "Call this tool again with user_confirmed=true to create the table"
            }

        # Build and execute CREATE TABLE
        column_defs = ["id UUID PRIMARY KEY DEFAULT gen_random_uuid()"]
        for col in columns:
            col_def = f"{col['name']} {col['type'].upper()}"
            if not col.get("nullable", True):
                col_def += " NOT NULL"
            if col.get("default"):
                col_def += f" DEFAULT {col['default']}"
            if col.get("unique"):
                col_def += " UNIQUE"
            column_defs.append(col_def)
        column_defs.append("created_at TIMESTAMPTZ DEFAULT NOW()")
        column_defs.append("updated_at TIMESTAMPTZ DEFAULT NOW()")

        create_sql = f"CREATE TABLE {table_name} ({', '.join(column_defs)})"

        result = supabase.rpc("exec_sql", {"query": create_sql}).execute()

        logger.info(f"Created table: {table_name}")
        return {
            "status": "success",
            "message": f"Table '{table_name}' created successfully",
            "table_name": table_name,
            "columns_created": len(columns) + 3
        }
    except Exception as e:
        error_msg = str(e)
        if "function" in error_msg.lower() and "does not exist" in error_msg.lower():
            return {
                "error": "Database does not support direct DDL. Table creation requires manual setup or admin access.",
                "workaround": "Ask the user to create the table manually in Supabase dashboard"
            }
        logger.error(f"Failed to create table: {e}")
        return {"error": str(e)}


def _add_column_to_table(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Add a column to an existing table."""
    try:
        table_name = tool_input.get("table_name", "").lower().strip()
        column_name = tool_input.get("column_name", "").lower().strip()
        column_type = tool_input.get("column_type", "").upper()
        nullable = tool_input.get("nullable", True)
        default_value = tool_input.get("default_value")
        user_confirmed = tool_input.get("user_confirmed", False)

        if not all([table_name, column_name, column_type]):
            return {"error": "table_name, column_name, and column_type are required"}

        # Validate table name format to prevent SQL injection
        if not re.match(r'^[a-z][a-z0-9_]*$', table_name):
            return {"error": "Table name must start with a letter and contain only lowercase letters, numbers, underscores"}

        # Validate column name format to prevent SQL injection
        if not re.match(r'^[a-z][a-z0-9_]*$', column_name):
            return {"error": "Column name must start with a letter and contain only lowercase letters, numbers, underscores"}

        # Validate column type against allowed PostgreSQL types
        allowed_types = [
            "TEXT", "INTEGER", "INT", "BIGINT", "SMALLINT",
            "BOOLEAN", "BOOL", "TIMESTAMPTZ", "TIMESTAMP",
            "UUID", "JSONB", "JSON", "FLOAT", "DOUBLE PRECISION",
            "NUMERIC", "DECIMAL", "DATE", "TIME", "SERIAL",
            "VARCHAR", "CHAR",
        ]
        # Allow types with length specifier like VARCHAR(255)
        base_type = re.match(r'^([A-Z ]+)', column_type)
        if not base_type or base_type.group(1).strip() not in allowed_types:
            return {"error": f"Column type '{column_type}' is not an allowed PostgreSQL type. Allowed: {', '.join(allowed_types)}"}

        # Validate default_value to prevent SQL injection
        if default_value and re.search(r'[;\'\"\\]', default_value):
            return {"error": "Default value contains forbidden characters (;, quotes, backslash)"}

        if not user_confirmed:
            alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            if not nullable:
                alter_sql += " NOT NULL"
            if default_value:
                alter_sql += f" DEFAULT {default_value}"

            return {
                "status": "CONFIRMATION_REQUIRED",
                "message": f"Ready to add column '{column_name}' to table '{table_name}'",
                "preview_sql": alter_sql,
                "instructions": "Call this tool again with user_confirmed=true to add the column"
            }

        alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
        if not nullable:
            alter_sql += " NOT NULL"
        if default_value:
            alter_sql += f" DEFAULT {default_value}"

        result = supabase.rpc("exec_sql", {"query": alter_sql}).execute()

        logger.info(f"Added column {column_name} to {table_name}")
        return {
            "status": "success",
            "message": f"Column '{column_name}' added to table '{table_name}'",
            "column_type": column_type
        }
    except Exception as e:
        error_msg = str(e)
        if "function" in error_msg.lower() and "does not exist" in error_msg.lower():
            return {
                "error": "Database does not support direct DDL via API",
                "workaround": "Add the column manually in Supabase dashboard: Table Editor -> Select table -> Add Column"
            }
        logger.error(f"Failed to add column: {e}")
        return {"error": str(e)}


def _update_data_batch(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Update multiple records in a single operation with verification."""
    try:
        table_name = tool_input.get("table_name", "").strip()
        updates = tool_input.get("updates", [])
        user_confirmed = tool_input.get("user_confirmed", False)

        if not table_name:
            return {"error": "table_name is required"}

        if not updates:
            return {"error": "updates array is required and must not be empty"}

        if len(updates) > 100:
            return {"error": f"Maximum 100 updates per batch (got {len(updates)}). Split into multiple calls."}

        # Validate all updates have IDs
        for i, update in enumerate(updates):
            if not update.get("id"):
                return {"error": f"Update #{i+1} missing required 'id' field"}

        if table_name not in WRITABLE_TABLES:
            return {
                "error": f"Table '{table_name}' is not writable",
                "allowed_tables": WRITABLE_TABLES
            }

        if not user_confirmed:
            preview = []
            for update in updates[:10]:
                record_id = update.get("id")
                fields = {k: v for k, v in update.items() if k != "id"}
                preview.append({
                    "id": record_id[:8] + "...",
                    "fields_to_update": list(fields.keys()),
                    "sample_values": {k: str(v)[:50] for k, v in list(fields.items())[:3]}
                })

            return {
                "status": "confirmation_required",
                "table": table_name,
                "total_updates": len(updates),
                "preview": preview,
                "message": f"This will UPDATE {len(updates)} records in '{table_name}'. Please confirm.",
                "instructions": "Ask the user to confirm ALL updates, then call update_data_batch again with user_confirmed=true"
            }

        # Execute all updates
        results = []
        errors = []
        updated_ids = []

        logger.info(f"Starting batch update of {len(updates)} records in '{table_name}'")

        for update in updates:
            record_id = update.get("id")
            fields = {k: v for k, v in update.items() if k != "id"}

            fields["updated_at"] = datetime.now(timezone.utc).isoformat()

            if table_name in SYNC_MANAGED_TABLES:
                fields["last_sync_source"] = "supabase"

            try:
                supabase.table(table_name).update(fields).eq("id", record_id).execute()

                verify = supabase.table(table_name).select("id").eq("id", record_id).execute()

                if verify.data and len(verify.data) > 0:
                    results.append({
                        "id": record_id,
                        "status": "updated",
                        "fields": list(fields.keys())
                    })
                    updated_ids.append(record_id)
                else:
                    errors.append({
                        "id": record_id,
                        "error": "Record not found after update attempt"
                    })
            except Exception as e:
                logger.error(f"Update failed for {record_id}: {e}")
                errors.append({
                    "id": record_id,
                    "error": str(e)
                })

        # Build response
        response = {
            "table": table_name,
            "requested_updates": len(updates),
            "updated_count": len(results),
            "failed_count": len(errors),
        }

        if len(errors) == 0 and len(results) == len(updates):
            response["status"] = "success"
            response["message"] = f"Successfully updated ALL {len(results)} records in '{table_name}'"
        elif len(results) > 0:
            response["status"] = "partial_success"
            response["message"] = f"Updated {len(results)}/{len(updates)} records in '{table_name}' ({len(errors)} failed)"
        else:
            response["status"] = "failed"
            response["message"] = f"FAILED: No records were updated in '{table_name}'"

        response["results"] = results[:20]
        if errors:
            response["errors"] = errors[:10]

        logger.info(f"Batch update complete: {response['status']} - {response['message']}")
        return response

    except Exception as e:
        logger.error(f"Failed to batch update: {e}")
        return {
            "status": "error",
            "error": str(e),
            "message": f"BATCH UPDATE FAILED: {str(e)}"
        }


def _insert_data_batch(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Insert multiple rows into a table."""
    try:
        table_name = tool_input.get("table_name", "").strip()
        rows = tool_input.get("rows", [])

        if not table_name:
            return {"error": "table_name is required"}

        if not rows:
            return {"error": "rows array is required and must not be empty"}

        if len(rows) > 100:
            return {"error": f"Maximum 100 rows per batch (got {len(rows)}). Split into multiple calls."}

        # Enforce writable table whitelist
        if table_name not in WRITABLE_TABLES:
            if table_name in READONLY_TABLES:
                return {"error": f"Table '{table_name}' is read-only (sync-managed). Cannot insert."}
            return {"error": f"Table '{table_name}' is not in the allowed writable tables list."}

        result = supabase.table(table_name).insert(rows).execute()

        inserted_count = len(result.data) if result.data else 0

        return {
            "status": "success",
            "message": f"Inserted {inserted_count} rows into '{table_name}'",
            "inserted_count": inserted_count,
            "sample_ids": [r.get("id") for r in (result.data or [])[:5]]
        }
    except Exception as e:
        logger.error(f"Failed to insert data: {e}")
        return {"error": str(e)}


def _get_database_backup_status(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Check backup status and recent backups."""
    try:
        # Check Supabase Storage for backups
        try:
            backups = supabase.storage.from_("backups").list()
            backup_files = [
                {
                    "name": f.get("name"),
                    "size": f.get("metadata", {}).get("size", "unknown"),
                    "created": f.get("created_at")
                }
                for f in (backups or [])
            ]
        except:
            backup_files = []

        # Check sync_logs for backup events
        try:
            logs = supabase.table("sync_logs").select("*").eq("event_type", "backup").order("created_at", desc=True).limit(10).execute()
            recent_backup_logs = logs.data or []
        except:
            recent_backup_logs = []

        return {
            "status": "success",
            "supabase_plan_info": "FREE TIER - No automatic backups! Only Pro plan ($25/month) includes daily backups.",
            "backup_storage_files": backup_files[:10],
            "recent_backup_logs": recent_backup_logs,
            "manual_backup_available": True,
            "warning": "YOU ARE ON FREE TIER - Use backup_table tool regularly to create manual backups!",
            "recommendation": "Consider upgrading to Supabase Pro for automatic daily backups with 7-day retention"
        }
    except Exception as e:
        logger.error(f"Failed to get backup status: {e}")
        return {"error": str(e)}


def _backup_table(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Create a backup of a specific table."""
    try:
        table_name = tool_input.get("table_name", "").strip()

        if not table_name:
            return {"error": "table_name is required"}

        # Fetch all data from table (with pagination for large tables)
        all_rows = []
        page_size = 1000
        start = 0

        while True:
            result = supabase.table(table_name).select("*").range(start, start + page_size - 1).execute()
            batch = result.data or []
            all_rows.extend(batch)
            if len(batch) < page_size:
                break
            start += page_size
            if start > 10000:
                break

        if not all_rows:
            return {
                "status": "warning",
                "message": f"Table '{table_name}' is empty - nothing to backup"
            }

        # Create backup JSON
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{table_name}_backup_{timestamp}.json"
        json_content = json.dumps(all_rows, indent=2, default=str)

        # Upload to Supabase Storage
        try:
            supabase.storage.from_("backups").upload(
                path=filename,
                file=json_content.encode('utf-8'),
                file_options={"content-type": "application/json", "upsert": "true"}
            )
            storage_status = "uploaded"
        except Exception as e:
            storage_status = f"upload failed: {str(e)[:50]}"

        # Log the backup
        try:
            supabase.table("sync_logs").insert({
                "event_type": "backup",
                "status": "success",
                "message": f"Backed up {len(all_rows)} rows from {table_name}",
                "details": {"table": table_name, "rows": len(all_rows), "filename": filename}
            }).execute()
        except:
            pass

        return {
            "status": "success",
            "message": f"Backed up {len(all_rows)} rows from '{table_name}'",
            "filename": filename,
            "rows_backed_up": len(all_rows),
            "storage_status": storage_status
        }
    except Exception as e:
        logger.error(f"Failed to backup table: {e}")
        return {"error": str(e)}
