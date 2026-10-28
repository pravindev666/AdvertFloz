#!/usr/bin/env python3
"""Validate campaign_plan.csv and one or more AdvertFloz image ZIP parts. Local-only."""
import argparse, csv, json, re, sys, zipfile
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PLAN_HEADER = ['post_id','scheduled_at','timezone','platforms','image_id','caption','enabled','campaign_tag','facebook_caption','instagram_caption','alt_text','destination_url','grace_minutes','ai_disclosure_status','notes']
PLATFORMS = {'facebook','instagram','facebook;instagram'}
DISCLOSURES = {'not_reviewed','not_required','required_pending','completed'}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--csv', required=True, type=Path)
    ap.add_argument('--zip', required=True, action='append', type=Path, help='Repeat for each ZIP part')
    ap.add_argument('--manifest', type=Path)
    ap.add_argument('--full-year', action='store_true')
    ap.add_argument('--max-image-bytes', type=int, default=8*1024*1024)
    ap.add_argument('--max-expanded-bytes', type=int, default=1_000_000_000)
    args=ap.parse_args(); errors=[]; warnings=[]
    try:
        with args.csv.open('r',encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            if reader.fieldnames != PLAN_HEADER:
                errors.append(f'Header mismatch; expected {PLAN_HEADER}; found {reader.fieldnames}')
            rows=list(reader)
    except Exception as e:
        print(f'Cannot read CSV: {e}',file=sys.stderr); return 2
    if not rows: errors.append('No campaign rows')
    post_ids=[]; image_ids=[]
    for line,row in enumerate(rows,start=2):
        pid=(row.get('post_id') or '').strip(); post_ids.append(pid)
        match=re.fullmatch(r'P(\d{3})',pid)
        ordinal=int(match.group(1)) if match else None
        if ordinal is None or not 1 <= ordinal <= 365: errors.append(f'Row {line}: post_id must be P001-P365')
        try:
            iid=int(row.get('image_id',''))
            if iid<1 or iid>365: raise ValueError
            image_ids.append(iid)
            if ordinal is not None and iid != ordinal: errors.append(f'Row {line} ({pid}): image_id must match post ordinal; expected {ordinal}')
        except Exception:
            iid=None; errors.append(f'Row {line} ({pid}): image_id must be integer 1-365')
        if row.get('enabled') != 'false': errors.append(f'Row {line} ({pid}): enabled must be exact lowercase false in external AI output')
        if row.get('platforms') not in PLATFORMS: errors.append(f'Row {line} ({pid}): invalid platforms value')
        raw=(row.get('scheduled_at') or '')
        try:
            dt=datetime.strptime(raw,'%Y-%m-%dT%H:%M:%S')
            if dt.strftime('%Y-%m-%dT%H:%M:%S') != raw: raise ValueError
        except Exception:
            dt=None; errors.append(f'Row {line} ({pid}): scheduled_at must be YYYY-MM-DDTHH:MM:SS')
        tzname=(row.get('timezone') or '').strip()
        try:
            tz=ZoneInfo(tzname)
            if dt:
                a0=dt.replace(tzinfo=tz,fold=0); a1=dt.replace(tzinfo=tz,fold=1)
                b0=a0.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
                b1=a1.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
                v0=b0==dt; v1=b1==dt
                if not v0 and not v1: errors.append(f'Row {line} ({pid}): nonexistent local time due to DST')
                elif v0 and v1 and a0.utcoffset()!=a1.utcoffset(): errors.append(f'Row {line} ({pid}): ambiguous local time due to DST')
        except ZoneInfoNotFoundError: errors.append(f'Row {line} ({pid}): unknown IANA timezone {tzname!r}')
        if (row.get('ai_disclosure_status') or '') not in DISCLOSURES: errors.append(f'Row {line} ({pid}): invalid ai_disclosure_status')
        if row.get('destination_url') and not row['destination_url'].startswith('https://'): errors.append(f'Row {line} ({pid}): destination_url must be blank or HTTPS')
        cap=(row.get('instagram_caption') or '').strip() or (row.get('caption') or '')
        if 'instagram' in (row.get('platforms') or '').split(';'):
            if len(cap)>2200: errors.append(f'Row {line} ({pid}): Instagram caption exceeds 2,200 chars')
            tags=re.findall(r'(?<![\w])#[\w]+',cap,flags=re.UNICODE)
            if len(tags)>5: warnings.append(f'Row {line} ({pid}): over five hashtags; conservative AdvertFloz policy, re-check current platform guidance')
        grace=(row.get('grace_minutes') or '').strip()
        if grace:
            try:
                value=int(grace)
                if not 0<=value<=1440: raise ValueError
            except Exception: errors.append(f'Row {line} ({pid}): grace_minutes must be blank or integer 0-1440')
    if len(post_ids)!=len(set(post_ids)): errors.append('Duplicate post_id values')
    if len(image_ids)!=len(set(image_ids)): errors.append('Duplicate image_id values')
    if args.full_year and sorted(post_ids)!=[f'P{i:03d}' for i in range(1,366)]: errors.append('Full-year mode requires exactly P001-P365')
    if len(rows)>365: errors.append('More than 365 rows')

    found={}; expanded=0
    for zpath in args.zip:
        if not zpath.is_file(): errors.append(f'ZIP not found: {zpath}'); continue
        try:
            with zipfile.ZipFile(zpath) as zf:
                infos=[info for info in zf.infolist() if not info.is_dir()]
                actual=set()
                for info in infos:
                    name=info.filename; p=PurePosixPath(name)
                    if p.is_absolute() or '..' in p.parts or len(p.parts)!=1 or '\\' in name:
                        errors.append(f'{zpath.name}: unsafe/non-flat path {name!r}'); continue
                    if not re.fullmatch(r'[1-9]\d{0,2}\.jpg',name):
                        errors.append(f'{zpath.name}: unexpected file {name!r}; expected numeric root JPEG such as 42.jpg'); continue
                    image_id=int(name[:-4]); actual.add(image_id); expanded+=info.file_size
                    if info.file_size>args.max_image_bytes: errors.append(f'{zpath.name}:{name}: exceeds configured image byte limit')
                    if expanded>args.max_expanded_bytes: errors.append('Total expanded bytes exceed configured limit'); break
                    if image_id in found: errors.append(f'Duplicate image ID {image_id} in {found[image_id]} and {zpath.name}'); continue
                    try: data=zf.read(info)
                    except Exception as e: errors.append(f'{zpath.name}:{name}: cannot read asset: {e}'); continue
                    if not data.startswith(b'\xff\xd8\xff'): errors.append(f'{zpath.name}:{name}: filename says JPG but bytes are not JPEG')
                    found[image_id]=zpath.name
                m=re.fullmatch(r'advertfloz_images_(\d{3})_(\d{3})\.zip',zpath.name)
                if m:
                    lo,hi=map(int,m.groups())
                    if actual != set(range(lo,hi+1)): errors.append(f'{zpath.name}: name range does not match contained IDs')
        except zipfile.BadZipFile: errors.append(f'Invalid ZIP: {zpath}')
        except Exception as e: errors.append(f'Cannot inspect {zpath}: {e}')
    for iid in set(image_ids):
        if iid not in found: errors.append(f'Missing referenced image `{iid}.jpg`')
    extras=set(found)-set(image_ids)
    if extras: warnings.append(f'Unused image IDs in ZIPs: {sorted(extras)[:30]}')

    if args.manifest:
        try:
            manifest=json.loads(args.manifest.read_text(encoding='utf-8-sig'))
            if manifest.get('schema_version')!='1.7': errors.append('Manifest schema_version must be "1.7"')
            if manifest.get('image_naming_pattern')!='{image_id}.jpg': errors.append('Manifest image_naming_pattern must be {image_id}.jpg')
            if manifest.get('enabled_default') is not False: errors.append('Manifest enabled_default must be boolean false')
            if manifest.get('post_count') not in (None,len(rows)): warnings.append('Manifest post_count differs from plan row count')
        except Exception as e: errors.append(f'Cannot read manifest: {e}')

    print('AdvertFloz package validation:', 'FAIL' if errors else ('PASS WITH WARNINGS' if warnings else 'PASS'))
    print(f'Plan rows: {len(rows)} | Images found: {len(found)} | ZIP-expanded bytes: {expanded}')
    print(f'Blocking errors: {len(errors)} | Warnings: {len(warnings)}')
    for msg in errors: print('ERROR:',msg)
    for msg in warnings: print('WARNING:',msg)
    return 1 if errors else 0

if __name__=='__main__': raise SystemExit(main())
