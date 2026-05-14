"""Pilot: Stage-3.5 visual audit for the /imgs_caption pipeline.

Picks N already-captioned rating>=3 images and, for each, asks joy_server to
identify factual mismatches between the stored caption_joy and what is
actually visible in the image. Output is a markdown file the curator reviews
by hand to calibrate the audit prompt before it gets wired into Stage 3.

Read-only against the DB — does NOT mutate caption_joy or any other field.
Edit the constants below and run.
"""
import datetime
import random
import sys
from pathlib import Path

from aidb import SceneDef, SceneManager
from ait.caption import joy_client

# ── configuration ────────────────────────────────────────────────────────
N_IMAGES = 20
SAMPLE_SEED = 42                     # reproducible sample across runs
MIN_RATING = 3
OUTPUT_MD = Path('/home/misw/Data/AI/audit/caption_audit_pilot_v2.md')

# Audit prompt under test. Iterate this between runs and compare outputs.
# Note: the joy_server runs with the capjoy LoRA ('default' adapter) active.
# The LoRA is tuned for caption generation, not for auditing — if precision
# is poor, the next pilot iteration should add a 'base' (no-adapter) mode to
# joy_server and try the audit there.
AUDIT_SYSTEM = (
    'You are an image audit assistant. You will be shown an image and a '
    'caption written by another captioning system. Your job is to identify '
    'CLEAR factual mismatches between the caption and what is actually '
    'visible in the image.\n\n'
    'IMPORTANT CONVENTIONS (read carefully):\n'
    '- The tokens "xlgts" and "xlasm" are model-specific identifier tokens, '
    'NOT content claims about the image. "xlgts" is the identifier for the '
    'woman; "xlasm" is the identifier for the adult man. Body-type modifier '
    'tokens such as "xlbusty", "xlmuscular", etc. attach to "xlgts woman". '
    'NEVER flag the presence or absence of these identifier tokens — they '
    'are tags the captioner is required to use, not visual claims to verify.\n'
    '- "xlgts woman" refers to the woman in the image. "xlasm man" refers '
    'to the adult man in the image. Audit claims about THEIR APPEARANCE, '
    'POSE, CLOTHING, and INTERACTION — not the tokens themselves.\n\n'
    'AUDIT RULES:\n'
    '- Flag a claim ONLY if it is clearly factually wrong. Examples of '
    'clear errors: caption says "naked" but figure is clothed; caption '
    'says "blonde hair" but hair is dark brown; caption says "stepping on" '
    'but the figure is sitting beside; caption says "wearing a dress" but '
    'figure is in a t-shirt.\n'
    '- Do NOT flag stylistic or synonym differences. Examples to IGNORE: '
    '"happy" vs "smiling", "neutral" vs "focused", "headboard" vs "frame", '
    '"bedroom" vs "indoor setting with bed and nightstand", "natural '
    'lighting" vs "soft lighting", "close-up" vs "three-quarter view".\n'
    '- Do NOT flag subjective interpretation (expression nuance, camera '
    'angle nuance, mood, lighting interpretation).\n'
    '- Do NOT invent facts the image does not show.\n'
    '- Most captions are mostly correct. If you are unsure whether '
    'something is wrong, do NOT flag it. Bias toward CLEAN.'
)

AUDIT_USER_TEMPLATE = '''Here is a caption written for this image:

"{caption}"

Identify CLEAR factual mismatches between the caption and the image.
Ignore the identifier tokens "xlgts" and "xlasm" — those are required
labels, not content claims.

For each mismatch, output one numbered line in the format:
  <N>. <specific caption claim> | <what the image actually shows>

If everything substantive matches (ignoring stylistic synonyms and the
xlgts/xlasm identifier tokens), output exactly:
  0. CLEAN

Bias toward CLEAN. Flag only obvious factual errors, not stylistic
choices, synonym differences, or subjective interpretation.'''


# ── pipeline ─────────────────────────────────────────────────────────────
def pick_sample(sim) -> list[dict]:
    coll = sim._dbc._get_collection(sim._collection_name)
    cur = coll.find(
        {
            SceneDef.FIELD_RATING: {'$gte': MIN_RATING},
            SceneDef.FIELD_CAPTION_JOY: {'$exists': True, '$nin': ['', None]},
        },
        {'_id': 1},
    )
    docs = list(cur)
    if not docs:
        return []
    random.seed(SAMPLE_SEED)
    return random.sample(docs, min(N_IMAGES, len(docs)))


def audit_one(image_path: str, caption: str) -> str:
    user_content = AUDIT_USER_TEMPLATE.format(caption=caption)
    try:
        _, audit = joy_client.caption(
            image_url=image_path,
            user_content=user_content,
            system_content=AUDIT_SYSTEM,
        )
        return audit
    except Exception as e:
        return f'[ERROR: {e}]'


def main() -> None:
    if not joy_client.is_running():
        print('joy_server is not running. start it first (`ait_server_joy` '
              'or `/joy_server start`).')
        sys.exit(1)

    scm = SceneManager(config='prod', verbose=0)
    sim = scm.scene_image_manager()
    sample = pick_sample(sim)
    if not sample:
        print(f'no eligible images (rating>={MIN_RATING} with caption_joy).')
        sys.exit(1)
    print(f'sampling {len(sample)} images (seed={SAMPLE_SEED}, '
          f'rating>={MIN_RATING})')

    lines: list[str] = []
    lines.append(f'# Caption Audit Pilot — {datetime.datetime.now().isoformat()}')
    lines.append('')
    lines.append(f'N={len(sample)}, seed={SAMPLE_SEED}, rating>={MIN_RATING}')
    lines.append('')
    lines.append('## Audit prompt under test')
    lines.append('')
    lines.append('System:')
    lines.append('```')
    lines.append(AUDIT_SYSTEM)
    lines.append('```')
    lines.append('')
    lines.append('User template:')
    lines.append('```')
    lines.append(AUDIT_USER_TEMPLATE)
    lines.append('```')
    lines.append('')
    lines.append('---')
    lines.append('')

    for i, doc in enumerate(sample, 1):
        img_id = str(doc['_id'])
        simg = sim.img_from_id(img_id)
        if simg is None:
            print(f'  [{i}/{len(sample)}] SKIP — image not loadable: {img_id}')
            continue
        caption = (simg.data.get(SceneDef.FIELD_CAPTION_JOY) or '').strip()
        img_path = simg.url_from_data
        if not img_path or not caption:
            print(f'  [{i}/{len(sample)}] SKIP — missing path or caption: {img_id}')
            continue
        print(f'  [{i}/{len(sample)}] {img_id} ...', flush=True)
        audit = audit_one(str(img_path), caption)
        lines.append(f'## {i}. `{img_id}`')
        lines.append(f'image: `{img_path}`')
        lines.append('')
        lines.append('caption_joy:')
        lines.append('```')
        lines.append(caption)
        lines.append('```')
        lines.append('audit output:')
        lines.append('```')
        lines.append(audit)
        lines.append('```')
        lines.append('')
        lines.append('---')
        lines.append('')

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text('\n'.join(lines))
    print(f'\nresults saved to {OUTPUT_MD}')
    print('open the file, read each (image, caption, audit) triple, and '
          'manually score precision/recall on real issues.')


if __name__ == '__main__':
    main()
