import sqlite3
import os


class UrtextCache:
    """SQLite cache for fast metadata, link, frame, and content queries."""

    SCHEMA_VERSION = 1

    _TABLES = [
        'frame_targets',
        'frames',
        'metadata_values',
        'metadata',
        'links',
        'settings',
        'nodes_fts',
        'nodes',
        'files',
    ]

    _CREATE_SCHEMA = """
        CREATE TABLE IF NOT EXISTS files (
            filename TEXT PRIMARY KEY,
            mtime REAL NOT NULL,
            content_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            filename TEXT NOT NULL,
            is_dynamic INTEGER NOT NULL DEFAULT 0,
            resolution TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_nodes_filename ON nodes(filename);
        CREATE INDEX IF NOT EXISTS idx_nodes_title ON nodes(title);

        CREATE TABLE IF NOT EXISTS metadata (
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            keyname TEXT NOT NULL,
            start_position INTEGER,
            end_position INTEGER,
            tag_self INTEGER NOT NULL DEFAULT 0,
            tag_children INTEGER NOT NULL DEFAULT 0,
            tag_descendants INTEGER NOT NULL DEFAULT 0,
            from_node_id TEXT,
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        );
        CREATE INDEX IF NOT EXISTS idx_metadata_keyname ON metadata(keyname);
        CREATE INDEX IF NOT EXISTS idx_metadata_node_id ON metadata(node_id);

        CREATE TABLE IF NOT EXISTS metadata_values (
            value_id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            value_text TEXT,
            value_lower TEXT,
            value_num REAL,
            timestamp_string TEXT,
            FOREIGN KEY (entry_id) REFERENCES metadata(entry_id)
        );
        CREATE INDEX IF NOT EXISTS idx_mv_entry_id ON metadata_values(entry_id);
        CREATE INDEX IF NOT EXISTS idx_mv_value_lower ON metadata_values(value_lower);

        CREATE TABLE IF NOT EXISTS links (
            link_id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_node_id TEXT NOT NULL,
            to_node_id TEXT NOT NULL,
            position_in_string INTEGER,
            is_pointer INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (from_node_id) REFERENCES nodes(id)
        );
        CREATE INDEX IF NOT EXISTS idx_links_from ON links(from_node_id);
        CREATE INDEX IF NOT EXISTS idx_links_to ON links(to_node_id);

        CREATE TABLE IF NOT EXISTS frames (
            frame_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_node_id TEXT NOT NULL,
            position INTEGER,
            end_position INTEGER,
            param_string TEXT,
            FOREIGN KEY (source_node_id) REFERENCES nodes(id)
        );

        CREATE TABLE IF NOT EXISTS frame_targets (
            target_id INTEGER PRIMARY KEY AUTOINCREMENT,
            frame_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            node_id TEXT,
            filename TEXT,
            matching_string TEXT,
            FOREIGN KEY (frame_id) REFERENCES frames(frame_id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            node_id TEXT NOT NULL,
            filename TEXT NOT NULL
        );
    """

    def __init__(self, db_path, project):
        """
        Open or create the cache database.

        Args:
            db_path: Path to .urtext_cache.db file
            project: The owning UrtextProject instance
        """
        self.db_path = db_path
        self.project = project
        self.conn = None
        self._available = False
        self._fts_available = False

        print('[CACHE DEBUG] UrtextCache.__init__ db_path: %s' % db_path)
        print('[CACHE DEBUG] db_path dir exists: %s' % os.path.exists(os.path.dirname(db_path)))

        try:
            self._open_database()
            print('[CACHE DEBUG] _open_database succeeded, available: %s' % self._available)
        except Exception as e:
            print('[CACHE DEBUG] _open_database FAILED: %s' % str(e))
            import traceback
            traceback.print_exc()
            # Attempt to delete corrupt file and recreate
            try:
                if os.path.exists(self.db_path):
                    self._close_connection()
                    os.remove(self.db_path)
                self._open_database()
            except Exception as e2:
                print('[CACHE DEBUG] recreate also FAILED: %s' % str(e2))
                self._close_connection()
                self._available = False

    def _open_database(self):
        """Open the SQLite database, enable WAL, check schema, create tables."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA foreign_keys=ON')

        current_version = self.conn.execute(
            'PRAGMA user_version').fetchone()[0]

        if current_version != self.SCHEMA_VERSION:
            self._drop_all_tables()
            self._create_schema()
            self.conn.execute(
                'PRAGMA user_version=%d' % self.SCHEMA_VERSION)
            self.conn.commit()
        else:
            # Tables should already exist, but ensure they do
            self._create_schema()
            self.conn.commit()

        self._available = True

    def _drop_all_tables(self):
        """Drop all cache tables in dependency order."""
        cursor = self.conn.cursor()
        for table in self._TABLES:
            if table == 'nodes_fts':
                cursor.execute('DROP TABLE IF EXISTS nodes_fts')
            else:
                cursor.execute('DROP TABLE IF EXISTS %s' % table)
        self.conn.commit()

    def _create_schema(self):
        """Create all tables and indexes."""
        self.conn.executescript(self._CREATE_SCHEMA)
        # FTS5 may not be available in all SQLite builds (e.g., Sublime Text's bundled Python)
        try:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5("
                "node_id, content, content='', tokenize='unicode61')")
            self.conn.commit()
            self._fts_available = True
        except Exception:
            self._fts_available = False

    def _close_connection(self):
        """Safely close the connection if open."""
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def _log_warning(self, message):
        """Log a warning through the project's logging mechanism."""
        if self.project:
            self.project.log_item('system', {
                'top_message': 'Cache: %s' % message
            })

    def close(self):
        """Close the database connection."""
        self._close_connection()
        self._available = False

    def is_available(self):
        """Return True if the cache database is open and usable."""
        return self._available and self.conn is not None

    # --- File Change Detection ---

    def get_changed_files(self, current_files):
        """
        Compare current file state against cached file records.

        Args:
            current_files: Dict mapping filename to content hash (SHA-256).

        Returns:
            Tuple of (changed_files, new_files, deleted_files).
            changed_files: files whose hash differs from cache.
            new_files: files not in cache.
            deleted_files: files in cache but not in current_files.
        """
        cursor = self.conn.execute(
            'SELECT filename, content_hash FROM files')
        cached = {row[0]: row[1] for row in cursor.fetchall()}

        current_set = set(current_files.keys())
        cached_set = set(cached.keys())

        new_files = current_set - cached_set
        deleted_files = cached_set - current_set
        changed_files = set()
        for filename in current_set & cached_set:
            if current_files[filename] != cached[filename]:
                changed_files.add(filename)

        return (changed_files, new_files, deleted_files)

    def update_file_record(self, filename, mtime, content_hash):
        """
        Update or insert a file record.

        Args:
            filename: The file path.
            mtime: File modification time.
            content_hash: SHA-256 hash of file contents.
        """
        self.conn.execute(
            'INSERT OR REPLACE INTO files (filename, mtime, content_hash) '
            'VALUES (?, ?, ?)',
            (filename, mtime, content_hash))
        self.conn.commit()

    def remove_file_record(self, filename):
        """
        Remove a file record and all associated cached data.

        Deletes in dependency order within a single transaction:
        frame_targets, frames, metadata_values, metadata, links,
        nodes_fts, nodes, and finally the files row.

        Args:
            filename: The file path to remove.
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute('BEGIN')

            # Get all node IDs for this file
            node_rows = cursor.execute(
                'SELECT id FROM nodes WHERE filename = ?',
                (filename,)).fetchall()
            node_ids = [row[0] for row in node_rows]

            if node_ids:
                placeholders = ','.join('?' * len(node_ids))

                # Delete frame_targets via frames
                cursor.execute(
                    'DELETE FROM frame_targets WHERE frame_id IN '
                    '(SELECT frame_id FROM frames WHERE source_node_id IN (%s))'
                    % placeholders,
                    node_ids)

                # Delete frames
                cursor.execute(
                    'DELETE FROM frames WHERE source_node_id IN (%s)'
                    % placeholders,
                    node_ids)

                # Delete metadata_values via metadata
                cursor.execute(
                    'DELETE FROM metadata_values WHERE entry_id IN '
                    '(SELECT entry_id FROM metadata WHERE node_id IN (%s))'
                    % placeholders,
                    node_ids)

                # Delete metadata
                cursor.execute(
                    'DELETE FROM metadata WHERE node_id IN (%s)'
                    % placeholders,
                    node_ids)

                # Delete links (from_node_id)
                cursor.execute(
                    'DELETE FROM links WHERE from_node_id IN (%s)'
                    % placeholders,
                    node_ids)

                # Delete FTS entries
                if self._fts_available:
                    cursor.execute(
                        'DELETE FROM nodes_fts WHERE node_id IN (%s)'
                        % placeholders,
                        node_ids)

                # Delete nodes
                cursor.execute(
                    'DELETE FROM nodes WHERE filename = ?',
                    (filename,))

            # Delete the file record
            cursor.execute(
                'DELETE FROM files WHERE filename = ?',
                (filename,))

            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # --- Write (post-compilation population) ---

    def populate_file(self, filename, nodes, mtime, content_hash):
        """
        Write all cached data for a single file.

        Within a single transaction: delete existing data for the file,
        then insert fresh data from in-memory node objects, and upsert
        the files table record.

        Args:
            filename: The file path.
            nodes: List of UrtextNode objects belonging to this file.
            mtime: File modification time.
            content_hash: SHA-256 hash of file contents.
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute('BEGIN')

            # 1. Delete existing data for this file (same cascade as remove_file_record)
            node_rows = cursor.execute(
                'SELECT id FROM nodes WHERE filename = ?',
                (filename,)).fetchall()
            old_node_ids = [row[0] for row in node_rows]

            if old_node_ids:
                placeholders = ','.join('?' * len(old_node_ids))

                cursor.execute(
                    'DELETE FROM frame_targets WHERE frame_id IN '
                    '(SELECT frame_id FROM frames WHERE source_node_id IN (%s))'
                    % placeholders,
                    old_node_ids)

                cursor.execute(
                    'DELETE FROM frames WHERE source_node_id IN (%s)'
                    % placeholders,
                    old_node_ids)

                cursor.execute(
                    'DELETE FROM metadata_values WHERE entry_id IN '
                    '(SELECT entry_id FROM metadata WHERE node_id IN (%s))'
                    % placeholders,
                    old_node_ids)

                cursor.execute(
                    'DELETE FROM metadata WHERE node_id IN (%s)'
                    % placeholders,
                    old_node_ids)

                cursor.execute(
                    'DELETE FROM links WHERE from_node_id IN (%s)'
                    % placeholders,
                    old_node_ids)

                if self._fts_available:
                    cursor.execute(
                        'DELETE FROM nodes_fts WHERE node_id IN (%s)'
                        % placeholders,
                        old_node_ids)

                cursor.execute(
                    'DELETE FROM nodes WHERE filename = ?',
                    (filename,))

            # 2. Insert fresh data from in-memory node objects
            for node in nodes:
                # Clean up any existing data for this node ID (may exist
                # from a different file if the node moved between files)
                existing = cursor.execute(
                    'SELECT id FROM nodes WHERE id = ?',
                    (node.id,)).fetchone()
                if existing:
                    cursor.execute(
                        'DELETE FROM frame_targets WHERE frame_id IN '
                        '(SELECT frame_id FROM frames WHERE source_node_id = ?)',
                        (node.id,))
                    cursor.execute(
                        'DELETE FROM frames WHERE source_node_id = ?',
                        (node.id,))
                    cursor.execute(
                        'DELETE FROM metadata_values WHERE entry_id IN '
                        '(SELECT entry_id FROM metadata WHERE node_id = ?)',
                        (node.id,))
                    cursor.execute(
                        'DELETE FROM metadata WHERE node_id = ?',
                        (node.id,))
                    cursor.execute(
                        'DELETE FROM links WHERE from_node_id = ?',
                        (node.id,))
                    if self._fts_available:
                        cursor.execute(
                            'DELETE FROM nodes_fts WHERE node_id = ?',
                            (node.id,))
                    cursor.execute(
                        'DELETE FROM nodes WHERE id = ?',
                        (node.id,))

                # Insert node
                cursor.execute(
                    'INSERT INTO nodes (id, title, filename, is_dynamic, resolution) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (node.id,
                     node.title,
                     node.filename,
                     1 if node.is_dynamic else 0,
                     node.resolution))

                # Insert metadata entries and values
                for entry in node.metadata.entries():
                    from_node_id = None
                    if entry.from_node and entry.from_node != node:
                        from_node_id = entry.from_node.id

                    cursor.execute(
                        'INSERT INTO metadata '
                        '(node_id, keyname, start_position, end_position, '
                        'tag_self, tag_children, tag_descendants, from_node_id) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (node.id,
                         entry.keyname,
                         entry.start_position,
                         entry.end_position,
                         1 if entry.tag_self else 0,
                         1 if entry.tag_children else 0,
                         1 if entry.tag_descendants else 0,
                         from_node_id))
                    entry_id = cursor.lastrowid

                    for v in entry.meta_values:
                        value_num = None
                        if v.text:
                            num = v.num()
                            if num != float('inf'):
                                value_num = num

                        timestamp_string = None
                        if v.timestamp and v.timestamp.datetime:
                            timestamp_string = v.timestamp.datetime.isoformat()

                        cursor.execute(
                            'INSERT INTO metadata_values '
                            '(entry_id, value_text, value_lower, value_num, timestamp_string) '
                            'VALUES (?, ?, ?, ?, ?)',
                            (entry_id,
                             v.text,
                             v.text_lower,
                             value_num,
                             timestamp_string))

                # Insert links (only node-to-node and pointer links)
                for link in node.links:
                    if link.is_node or link.is_pointer:
                        cursor.execute(
                            'INSERT INTO links '
                            '(from_node_id, to_node_id, position_in_string, is_pointer) '
                            'VALUES (?, ?, ?, ?)',
                            (node.id,
                             link.node_id,
                             link.position_in_string,
                             1 if link.is_pointer else 0))

                # Insert frames (from project.frames, the authoritative source)
                for frame in self.project.frames.get(node.id, []):
                    cursor.execute(
                        'INSERT INTO frames '
                        '(source_node_id, position, end_position, param_string) '
                        'VALUES (?, ?, ?, ?)',
                        (node.id,
                         frame.position,
                         frame.end_position,
                         frame.param_string))
                    frame_id = cursor.lastrowid

                    for target in frame.targets:
                        if target.is_virtual:
                            target_type = 'virtual'
                        elif target.is_file:
                            target_type = 'file'
                        else:
                            target_type = 'node'

                        cursor.execute(
                            'INSERT INTO frame_targets '
                            '(frame_id, target_type, node_id, filename, matching_string) '
                            'VALUES (?, ?, ?, ?, ?)',
                            (frame_id,
                             target_type,
                             target.node_id,
                             getattr(target, 'filename', None),
                             target.matching_string))

                # Insert FTS entry for non-dynamic nodes
                if self._fts_available and not node.is_dynamic:
                    cursor.execute(
                        'INSERT INTO nodes_fts (node_id, content) '
                        'VALUES (?, ?)',
                        (node.id, node.stripped_contents))

            # 3. Upsert the files table record
            cursor.execute(
                'INSERT OR REPLACE INTO files (filename, mtime, content_hash) '
                'VALUES (?, ?, ?)',
                (filename, mtime, content_hash))

            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def remove_file(self, filename):
        """
        Remove all cached data for a file.

        Delegates to remove_file_record which handles the cascade
        deletion across all tables.

        Args:
            filename: The file path to remove.
        """
        self.remove_file_record(filename)

    def update_node_dynamic_flag(self, node_id, is_dynamic):
        """
        Update the is_dynamic flag for a node after _mark_dynamic_nodes runs.

        Args:
            node_id: The node ID to update.
            is_dynamic: Boolean indicating whether the node is dynamic.
        """
        self.conn.execute(
            'UPDATE nodes SET is_dynamic = ? WHERE id = ?',
            (1 if is_dynamic else 0, node_id))
        self.conn.commit()

    # --- Settings ---

    def write_settings(self, settings_nodes):
        """
        Write all settings from project_settings nodes to cache.

        Replaces all existing settings rows. For each node, iterates
        its metadata entries and writes key-value pairs to the settings table.

        Args:
            settings_nodes: List of UrtextNode objects that are project_settings nodes.
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute('BEGIN')

            # Delete all existing settings
            cursor.execute('DELETE FROM settings')

            # Insert fresh settings from each node
            for node in settings_nodes:
                for entry in node.metadata.entries():
                    for v in entry.meta_values:
                        cursor.execute(
                            'INSERT INTO settings (key, value, node_id, filename) '
                            'VALUES (?, ?, ?, ?)',
                            (entry.keyname,
                             v.text,
                             node.id,
                             node.filename))

            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def get_cached_settings(self):
        """
        Load all cached settings.

        Returns:
            Dict mapping setting key to list of
            {'value': str, 'node_id': str, 'filename': str} dicts.
        """
        cursor = self.conn.execute(
            'SELECT key, value, node_id, filename FROM settings')
        result = {}
        for row in cursor.fetchall():
            key = row[0]
            entry = {
                'value': row[1],
                'node_id': row[2],
                'filename': row[3],
            }
            if key not in result:
                result[key] = []
            result[key].append(entry)
        return result

    # --- Read (query paths) ---

    def query_by_meta(self, key, values, operator,
                      excluded_keys=None,
                      numerical_keys=None,
                      case_sensitive_keys=None):
        """
        Query nodes by metadata key-value pairs.

        Args:
            key: Metadata keyname to query, or '*' for all keys.
            values: List of values to match.
            operator: Query operator ('before', 'after', or default '=').
            excluded_keys: Keys to exclude when key is '*'.
            numerical_keys: Keys whose values should be compared numerically.
            case_sensitive_keys: Keys whose values should be compared case-sensitively.

        Returns:
            List of distinct node IDs matching the query.
        """
        if excluded_keys is None:
            excluded_keys = []
        if numerical_keys is None:
            numerical_keys = []
        if case_sensitive_keys is None:
            case_sensitive_keys = []

        results = set()

        if operator in ('before', 'after'):
            # Timestamp comparison using timestamp_string column
            from urtext.timestamp import date_from_timestamp
            compare_date = date_from_timestamp(values[0][1:-1])
            if compare_date:
                compare_iso = compare_date.isoformat()
                if operator == 'before':
                    sql_op = '<'
                else:
                    sql_op = '>'
                cursor = self.conn.execute(
                    'SELECT DISTINCT m.node_id FROM metadata m '
                    'JOIN metadata_values mv ON mv.entry_id = m.entry_id '
                    'WHERE m.keyname = ? '
                    'AND mv.timestamp_string IS NOT NULL '
                    'AND mv.timestamp_string %s ?' % sql_op,
                    (key, compare_iso))
                results.update(row[0] for row in cursor.fetchall())
            return list(results)

        for value in values:
            if key == '*':
                # Wildcard key: query across all keynames, excluding specified keys
                if excluded_keys:
                    placeholders = ','.join('?' * len(excluded_keys))
                    base_sql = (
                        'SELECT DISTINCT m.node_id FROM metadata m '
                        'JOIN metadata_values mv ON mv.entry_id = m.entry_id '
                        'WHERE m.keyname NOT IN (%s) '
                        'AND mv.value_lower = ?' % placeholders)
                    params = excluded_keys + [value.lower() if isinstance(value, str) else value]
                else:
                    base_sql = (
                        'SELECT DISTINCT m.node_id FROM metadata m '
                        'JOIN metadata_values mv ON mv.entry_id = m.entry_id '
                        'WHERE mv.value_lower = ?')
                    params = [value.lower() if isinstance(value, str) else value]
                cursor = self.conn.execute(base_sql, params)
                results.update(row[0] for row in cursor.fetchall())

            elif value == '*':
                # Wildcard value: return all nodes with any metadata for this key
                cursor = self.conn.execute(
                    'SELECT DISTINCT node_id FROM metadata WHERE keyname = ?',
                    (key,))
                results.update(row[0] for row in cursor.fetchall())

            elif key in numerical_keys:
                # Numeric comparison using value_num column
                try:
                    num_value = float(value)
                except (ValueError, TypeError):
                    num_value = float('inf')
                cursor = self.conn.execute(
                    'SELECT DISTINCT m.node_id FROM metadata m '
                    'JOIN metadata_values mv ON mv.entry_id = m.entry_id '
                    'WHERE m.keyname = ? AND mv.value_num = ?',
                    (key, num_value))
                results.update(row[0] for row in cursor.fetchall())

            elif key in case_sensitive_keys:
                # Case-sensitive comparison using value_text column
                cursor = self.conn.execute(
                    'SELECT DISTINCT m.node_id FROM metadata m '
                    'JOIN metadata_values mv ON mv.entry_id = m.entry_id '
                    'WHERE m.keyname = ? AND mv.value_text = ?',
                    (key, value))
                results.update(row[0] for row in cursor.fetchall())

            elif hasattr(value, 'datetime'):
                # UrtextTimestamp value: compare against timestamp_string
                timestamp_iso = value.datetime.isoformat()
                cursor = self.conn.execute(
                    'SELECT DISTINCT m.node_id FROM metadata m '
                    'JOIN metadata_values mv ON mv.entry_id = m.entry_id '
                    'WHERE m.keyname = ? AND mv.timestamp_string = ?',
                    (key, timestamp_iso))
                results.update(row[0] for row in cursor.fetchall())

            else:
                # Default: case-insensitive match on value_lower
                lower_value = value.lower() if isinstance(value, str) else value
                cursor = self.conn.execute(
                    'SELECT DISTINCT m.node_id FROM metadata m '
                    'JOIN metadata_values mv ON mv.entry_id = m.entry_id '
                    'WHERE m.keyname = ? AND mv.value_lower = ?',
                    (key, lower_value))
                results.update(row[0] for row in cursor.fetchall())

        return list(results)

    def query_links_to(self, to_node_id, include_dynamic=True):
        """
        Query nodes that link to the given node.

        Args:
            to_node_id: The target node ID.
            include_dynamic: If False, exclude links from dynamic nodes.

        Returns:
            List of from_node_id values that link to to_node_id.
        """
        if include_dynamic:
            cursor = self.conn.execute(
                'SELECT DISTINCT from_node_id FROM links '
                'WHERE to_node_id = ?',
                (to_node_id,))
        else:
            cursor = self.conn.execute(
                'SELECT DISTINCT l.from_node_id FROM links l '
                'JOIN nodes n ON n.id = l.from_node_id '
                'WHERE l.to_node_id = ? AND n.is_dynamic = 0',
                (to_node_id,))
        return [row[0] for row in cursor.fetchall()]

    def query_links_from(self, from_node_id, include_dynamic=True):
        """
        Query nodes that the given node links to.

        Args:
            from_node_id: The source node ID.
            include_dynamic: If False, exclude links to dynamic nodes.

        Returns:
            List of to_node_id values that from_node_id links to.
        """
        if include_dynamic:
            cursor = self.conn.execute(
                'SELECT DISTINCT to_node_id FROM links '
                'WHERE from_node_id = ?',
                (from_node_id,))
        else:
            cursor = self.conn.execute(
                'SELECT DISTINCT l.to_node_id FROM links l '
                'JOIN nodes n ON n.id = l.to_node_id '
                'WHERE l.from_node_id = ? AND n.is_dynamic = 0',
                (from_node_id,))
        return [row[0] for row in cursor.fetchall()]

    def query_fts(self, search_term):
        """
        Full-text search pre-filter.

        Queries the nodes_fts FTS5 table, excluding dynamic nodes.
        Wraps each word with * for prefix matching to improve recall.

        Args:
            search_term: The search string.

        Returns:
            List of candidate node IDs. Caller must verify with
            Python substring matching. Returns empty list if FTS5
            is not available.
        """
        if not self._fts_available:
            return []
        try:
            # Build FTS5 query: wrap each word with * for prefix matching
            words = search_term.strip().split()
            if not words:
                return []
            fts_terms = ' '.join('%s*' % word for word in words)

            cursor = self.conn.execute(
                'SELECT nf.node_id FROM nodes_fts nf '
                'JOIN nodes n ON n.id = nf.node_id '
                'WHERE nodes_fts MATCH ? AND n.is_dynamic = 0',
                (fts_terms,))
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []

    def query_all_keys(self, excluded_keys=None):
        """
        Get all unique metadata keys with occurrence counts.

        Args:
            excluded_keys: List of keynames to exclude.

        Returns:
            Dict mapping keyname to count.
        """
        if excluded_keys:
            placeholders = ','.join('?' * len(excluded_keys))
            cursor = self.conn.execute(
                'SELECT keyname, COUNT(*) as cnt FROM metadata '
                'WHERE keyname NOT IN (%s) '
                'GROUP BY keyname' % placeholders,
                excluded_keys)
        else:
            cursor = self.conn.execute(
                'SELECT keyname, COUNT(*) as cnt FROM metadata '
                'GROUP BY keyname')
        return {row[0]: row[1] for row in cursor.fetchall()}

    def query_all_values_for_key(self, key):
        """
        Get all unique values for a metadata key with occurrence counts.

        Args:
            key: The metadata keyname.

        Returns:
            Dict mapping value_text to count.
        """
        cursor = self.conn.execute(
            'SELECT mv.value_text, COUNT(*) as cnt '
            'FROM metadata_values mv '
            'JOIN metadata m ON mv.entry_id = m.entry_id '
            'WHERE m.keyname = ? '
            'GROUP BY mv.value_text',
            (key,))
        return {row[0]: row[1] for row in cursor.fetchall()}

    def query_duplicate_titles(self, title):
        """
        Find nodes with the given title.

        Args:
            title: The title to search for.

        Returns:
            List of node IDs with matching title.
        """
        cursor = self.conn.execute(
            'SELECT id FROM nodes WHERE title = ?',
            (title,))
        return [row[0] for row in cursor.fetchall()]
