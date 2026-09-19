"""Explicit create, lookup and verified adoption with interruption-safe state."""
import copy
import json
import shutil

from tts_app.providers.qwen_enrollment import CLONE_MODEL, preferred_name, validate_voice_id
from tts_app.voice_tools.audio import asset, sha256, validate_reference
from tts_app.voice_tools.common import new_run, timestamp
from tts_app.voice_tools.manifest import load_manifest, resolve_asset, save_manifest, validate_manifest, validate_speed
from tts_app.voice_tools.report import write_report


def selected_candidate(path, number):
    source = load_manifest(path)
    if source['kind'] != 'candidates':
        raise ValueError('Expected candidate manifest')
    sample = next((s for s in source['samples'] if s['number'] == number), None)
    if sample is None or sample['status'] != 'completed':
        raise ValueError('Candidate sample must exist and be completed')
    return source, sample


async def run(args, *, enrollment):
    if args.resume:
        path = args.resume
        manifest = load_manifest(path)
        if manifest['kind'] != 'voice' or len(manifest['voices']) != 1:
            raise ValueError('Enrollment recovery requires a single voice manifest')
        entry = manifest['voices'][0]
        if args.reference and sha256(args.reference) != entry['reference']['sha256']:
            raise ValueError('Resume reference identity differs')
        for supplied, saved in ((args.key, entry['key']), (args.name, entry['name']), (args.model, entry['target_model']), (args.speed, entry['speed'])):
            if supplied is not None and supplied != saved:
                raise ValueError('Resume settings identity differs')
        if args.output and args.output.resolve() != path.resolve().parent:
            raise ValueError('Resume output does not match manifest')
    else:
        if args.lookup or args.adopt_voice_id:
            raise ValueError('Recovery requires --resume manifest')
        if not args.reference or not args.name or not args.key or not args.output or args.output.exists():
            raise ValueError('Supply reference, name, key, and a new output directory')
        metadata = validate_reference(args.reference)
        model = args.model or CLONE_MODEL
        if model != CLONE_MODEL:
            raise ValueError('Unsupported clone target model')
        speed = args.speed if args.speed is not None else 1.0
        validate_speed(speed)
        provenance = {'kind': 'supplied', 'wav': metadata}
        if args.candidate_manifest:
            source, sample = selected_candidate(args.candidate_manifest, args.sample)
            if sample['settings']['language'] != 'English':
                raise ValueError('Enrollment currently supports English references only')
            if sha256(args.reference) != sample['audio']['sha256']:
                raise ValueError('Reference bytes differ from selected candidate')
            provenance |= {'kind': 'candidate', 'run_id': source['run_id'], 'sample_number': sample['number'], 'settings': copy.deepcopy(sample['settings']), 'text_sha256': sample['text_sha256'], 'text': {'path': 'reference.txt', 'sha256': source['text']['sha256']}}
        elif args.sample is not None:
            raise ValueError('--sample requires --candidate-manifest')
        entry = {'key': args.key, 'name': args.name, 'language': 'en', 'speed': speed,
                 'target_model': model, 'reference': {'path': 'reference.wav', 'sha256': sha256(args.reference), 'provenance': provenance},
                 'enrollment': None, 'comparisons': [], 'acceptance': None, 'status': 'queued', 'preferred_name': preferred_name(args.key)}
        path = args.output / 'manifest.json'
        manifest = {'schema_version': 1, 'kind': 'voice', 'run_id': 'pending', 'voices': [entry]}
        validate_manifest(manifest, path, verify_assets=False)
    if args.lookup:
        if args.check:
            print('1 read-only enrollment lookup; 0 creates; 0 writes')
        else:
            print(json.dumps(await enrollment.lookup(page_index=args.page_index), indent=2))
        return 0
    if args.adopt_voice_id:
        validate_voice_id(args.adopt_voice_id)
        if entry.get('enrollment'):
            raise ValueError('Voice already has a saved enrollment')
        if entry.get('endpoint_region') != enrollment.endpoint_region:
            raise ValueError('Recovery endpoint region differs')
        if entry.get('account_fingerprint') != enrollment.account_fingerprint and not args.acknowledge_credential_change:
            raise ValueError('Credential changed; verify account and use --acknowledge-credential-change')
        if args.check:
            print('1 read-only enrollment lookup and local adoption; 0 creates')
            return 0
        output = await enrollment.lookup(page_index=args.page_index)
        record = next((v for v in output.get('voice_list', []) if v.get('voice') == args.adopt_voice_id), None)
        if record is None or record.get('target_model') != entry['target_model']:
            raise ValueError('Voice not found in this account/region page with matching target model')
        entry['enrollment'] = {k: record[k] for k in ('voice', 'target_model', 'fallback_mode', 'fallback_reason') if k in record} | {
            'preferred_name': entry['preferred_name'], 'endpoint_region': enrollment.endpoint_region,
            'account_fingerprint': enrollment.account_fingerprint, 'request_id': None, 'adopted_at': timestamp()}
        entry.update(status='enrolled')
        entry.pop('error', None)
        save_manifest(path, manifest)
        write_report(path.parent / 'report.html', manifest)
        return 0
    if entry.get('enrollment'):
        print('Enrollment already saved; 0 requests')
        return 0
    if entry['status'] in {'enrolling', 'uncertain'}:
        raise ValueError('Enrollment outcome uncertain: use --lookup then --adopt-voice-id; create is never retried')
    print('1 enrollment request; 0 TTS requests')
    if args.check:
        return 0
    if not args.resume:
        manifest.update(new_run(path.parent, 'voice'))
        shutil.copyfile(args.reference, path.parent / 'reference.wav')
        if args.candidate_manifest:
            shutil.copyfile(resolve_asset(args.candidate_manifest, source['text']['path']), path.parent / 'reference.txt')
    entry.update(status='enrolling', endpoint_region=enrollment.endpoint_region, account_fingerprint=enrollment.account_fingerprint)
    save_manifest(path, manifest)
    try:
        entry['enrollment'] = await enrollment.create(resolve_asset(path, entry['reference']['path']), entry['preferred_name'])
        entry.update(status='enrolled')
    except (RuntimeError, TimeoutError, ValueError) as error:
        entry.update(status='uncertain', error=str(error) or type(error).__name__)
    save_manifest(path, manifest)
    write_report(path.parent / 'report.html', manifest)
    return int(entry['status'] != 'enrolled')
