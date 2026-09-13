"""Self-contained, escaped listening report with local relative audio links."""
from html import escape
from pathlib import Path
from urllib.parse import quote


def write_report(path: Path, manifest: dict):
    def e(value):
        return escape(str(value), quote=True)
    def player(record, label):
        if not record:
            return '<p>Audio unavailable; track incomplete.</p>'
        return f'<audio controls preload="none" aria-label="{e(label)}" src="{quote(record["path"], safe="/")}"></audio>'
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>Readvox voice workshop</title><style>body{font:16px system-ui;max-width:900px;margin:auto;padding:20px}audio{width:100%;max-width:600px}article{border-top:1px solid #aaa;padding:16px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>',
             f'<h1>Voice workshop</h1><p>Run: {e(manifest["run_id"])}</p>']
    for sample in manifest.get('samples', []):
        label = f'Sample {sample["number"]}: {sample["settings"]["voice"]} at {sample["settings"]["speed"]}×'
        parts += [f'<article><h2>{e(label)}</h2><p>{e(sample["status"])}</p>', player(sample.get('audio') if sample['status'] == 'completed' else None, label), f'<pre>{e(sample.get("error", ""))}</pre></article>']
    for voice in manifest.get('voices', []):
        parts += [f'<article><h2>{e(voice["name"])}</h2><p>{e(voice["key"])} · {e(voice.get("status", "unknown"))}</p>', player(voice['reference'], 'Reference for ' + voice['name']), f'<pre>{e(voice.get("error", ""))}</pre>']
        for comparison in voice['comparisons']:
            config = comparison['settings']
            label = f'{comparison["mode"]}: {config["voice"]} / {config["model"]} / {config["speed"]}×'
            parts += [f'<h3>{e(label)}</h3><p>Status: {e(comparison["status"])}</p>', player(comparison.get('audio') if comparison['status'] == 'completed' else None, label), f'<p>Measured passage starts (seconds): {e(comparison.get("boundaries", []))}</p>', f'<pre>{e(comparison.get("error", ""))}</pre>']
            for number, passage in enumerate(comparison.get('passages', []), 1):
                parts += [f'<p>Passage {number}: {e(passage["status"])}</p>', player(passage.get('audio') if passage['status'] == 'completed' else None, f'{label}, passage {number}')]
        parts += ['</article>']
    parts += ['</html>']
    path.write_text('\n'.join(parts), encoding='utf-8')
