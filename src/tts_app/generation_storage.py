"""Atomic generation claims and segment checkpoints; no provider calls."""


class GenerationConflict(RuntimeError):
    pass


class GenerationRecoveryStorageMixin:
    def claim_generation(self, generation_id, *, resume=False):
        expected = 'failed' if resume else 'queued'
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT status FROM generations WHERE id=?', (generation_id,)).fetchone()
            if row is None:
                raise KeyError(f'generation {generation_id} not found')
            if row['status'] != expected:
                raise GenerationConflict(f"Cannot {'resume' if resume else 'start'} a {row['status']} generation")
            conn.execute("UPDATE generations SET status='running', error=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?", (generation_id,))
            if resume:
                conn.execute("UPDATE text_segments SET status='queued', updated_at=CURRENT_TIMESTAMP WHERE generation_id=? AND status != 'completed'", (generation_id,))

    def interrupt_generations(self, generation_id=None):
        message = 'Generation interrupted by server shutdown or restart. Resume to continue unfinished segments.'
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            clause = "status IN ('queued','running')"
            params = ()
            if generation_id is not None:
                clause += ' AND id=?'
                params = (generation_id,)
            ids = [r['id'] for r in conn.execute(f'SELECT id FROM generations WHERE {clause}', params)]
            for gid in ids:
                conn.execute("UPDATE text_segments SET status='failed', updated_at=CURRENT_TIMESTAMP WHERE generation_id=? AND status='running'", (gid,))
                conn.execute("UPDATE generations SET status='failed', error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (message, gid))
        return ids

    def complete_audio_segment(self, *, generation_id, text_segment_id, segment_index, file_path, mime_type, duration_ms, byte_size):
        with self.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            cur = conn.execute('''INSERT INTO audio_segments
                (generation_id,text_segment_id,segment_index,file_path,mime_type,duration_ms,byte_size,status,error)
                VALUES (?,?,?,?,?,?,?,'completed',NULL)''',
                (generation_id,text_segment_id,segment_index,file_path,mime_type,duration_ms,byte_size))
            conn.execute("UPDATE text_segments SET status='completed', updated_at=CURRENT_TIMESTAMP WHERE id=? AND generation_id=?", (text_segment_id,generation_id))
            return int(cur.lastrowid)
