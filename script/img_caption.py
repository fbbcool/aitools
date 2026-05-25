import datetime
import shutil
import sys
from pathlib import Path
from typing import Optional

from aidb.scene.db_connect import DBConnection
from ait.caption import joy_client
from ait.caption.skin import SkinRegistry
from ait.tools.files import is_img

LOG_COLLECTION = 'ait-caption-log'

if __name__ == '__main__':
    url_img = Path(sys.argv[1])
    body_label: Optional[str] = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
    penis_flag: bool = len(sys.argv) > 3 and sys.argv[3] == '1'
    hint: str = sys.argv[4].strip() if len(sys.argv) > 4 else ''
    if not is_img(url_img):
        exit(1)
    print(f'-> {url_img.name}')

    sk = SkinRegistry().get('1xlasm')
    emphases: list[str] = []
    if body_label:
        desc = sk.labels.get(f'primary.attribute.{body_label}')
        if desc:
            emphases.append(desc)
        else:
            print(f'[warn] no skin rendering for primary.attribute.{body_label}')
    if penis_flag:
        desc = sk.labels.get('secondary.attribute.penis')
        if desc:
            emphases.append(desc)

    # Hint goes INSIDE the directive (recency slot before OUTPUT STYLE) instead
    # of through user_hint_preamble, whose training-flavor language fragments
    # the output. The directive template lives in 1xlasm.json's optional
    # `standalone` block (1xlasm-specific generation-mode prompt engineering).
    directive = sk.standalone_directive(emphases=tuple(emphases), hint=hint)

    # Route through the persistent joy_server (model stays loaded, ~5-10s
    # per call). The server is auto-started on first call if not already up.
    joy_client.ensure_running(skin='1xlasm')
    prompt, caption = joy_client.caption(
        image_url=str(url_img),
        user_content=directive,
        system_content=directive,
    )

    print(f'<caption>\n{caption}\n </caption>')

    try:
        dbc = DBConnection(config='prod', verbose=0)
        ts = datetime.datetime.now(datetime.timezone.utc)
        save_dir = dbc.config.ait_caption_url
        save_dir.mkdir(parents=True, exist_ok=True)
        saved_url = save_dir / f'{ts.strftime("%Y%m%dT%H%M%S")}_{url_img.name}'
        shutil.copy2(url_img, saved_url)
        dbc.insert_document(LOG_COLLECTION, {
            'ts': ts,
            'img_url': str(url_img),
            'saved_url': str(saved_url),
            'user_input': {
                'body_label': body_label,
                'penis': penis_flag,
                'hint': hint,
            },
            'caption_prompt': prompt,
            'caption_joy': caption,
        })
    except Exception as exc:
        print(f'[warn] {LOG_COLLECTION} log failed: {exc}')
