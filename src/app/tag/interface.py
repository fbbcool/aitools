from pathlib import Path
from typing import Any, Final, Literal
import gradio as gr
import numpy as np
from PIL import Image

from config import pools, Pool, TagsSummary, TagAction

TAG_NUM_PER_PAGE: Final = 100
IMG_NUM_GALLERY: Final = 100
IMG_SIZE: Final = 250
IMG_COLUMS = 4
CAPS_LINES = 10

LABEL_BUTT_GALLERY_ON: Final = "Hide Tags Gallery"
LABEL_BUTT_GALLERY_OFF: Final = "Show Tags Gallery"
LABEL_BUTT_GALLERY_ON_NOTAGS: Final = "Hide No Tags Gallery"
LABEL_BUTT_GALLERY_OFF_NOTAGS: Final = "Show No Tags Gallery"

img_empty = Image.new('RGB', (1, 1))
rows_galleries = [gr.Gallery(
    type="pil",
    preview=True,
    value=[img_empty],
    scale=1,
    columns=5,
    rows=2,
    height=300,
    selected_index=0,
    show_download_button=False,
    show_share_button=False,
    visible=False,
    elem_id=f"gallery_{i}"
    ) for i in range(TAG_NUM_PER_PAGE)]
rows_butt_galleries = [gr.Button(LABEL_BUTT_GALLERY_OFF,value=LABEL_BUTT_GALLERY_OFF, scale=1,visible=True, elem_id=f"but-gallery_{i}") for i in range(TAG_NUM_PER_PAGE)]
rows_butt_galleries_notags = [gr.Button(LABEL_BUTT_GALLERY_OFF_NOTAGS,value=LABEL_BUTT_GALLERY_OFF_NOTAGS, scale=1,visible=True, elem_id=f"but-gallery_{i}") for i in range(TAG_NUM_PER_PAGE)]
rows_tag = [gr.Textbox(value="",label="Tag",placeholder="empty", visible=True, elem_id=f"tag_{i}", interactive=False) for i in range(TAG_NUM_PER_PAGE)]
rows_tag_seq = {rows_tag[0]}
for tag in rows_tag: rows_tag_seq.add(tag)

rows_action = [gr.Radio(choices=["delete", "replace", "deselect", "deselect_notags", "no_action", "undef"],value="undef",label="Action", visible=True, interactive=True) for i in range(TAG_NUM_PER_PAGE)]
rows_payload = [gr.Textbox(value="",label="Payload",placeholder="empty", visible=True, interactive=True) for i in range(TAG_NUM_PER_PAGE)]

pool: Pool = Pool()

def hide_groups():
    return [gr.update(visible=False) for i in range(TAG_NUM_PER_PAGE)]

def show_groups(page: int):
    return [gr.update(visible=True) for i in range(TAG_NUM_PER_PAGE)]

def flush_tags():
    return [gr.update(value="") for i in range(TAG_NUM_PER_PAGE)]

def new_pool(poolname:str):
    global pool
    if poolname == "None":
        pool = Pool()
        return
    if pool.name != poolname:
        pool = Pool(poolname)
        if len(pool) <= 0:
            gr.Warning(f"Pool {poolname} is empty!")
            return
        gr.Info(f"Loading pool {poolname} ...")
    return

def new_page_idx(page:int) -> None:
    return [gr.update(value=TAG_NUM_PER_PAGE*(page-1) + i) for i in range(TAG_NUM_PER_PAGE)]

def new_pool_page(poolname:str) -> None:
    num = len(list(pool.tags.keys()))
    if num == 0:
        values = [1]
        return gr.update(choices=values, value=values[0])

    per = TAG_NUM_PER_PAGE
    pages = num // per + 1
    if num % per > 0:
        pages += 1
    values = [x for x in range(1,pages)]
    return gr.update(choices=values, value=values[0])

def switch_gallery(switch: str, tag: str):
    OFF = LABEL_BUTT_GALLERY_OFF
    ON = LABEL_BUTT_GALLERY_ON
    ret_off = (gr.update(value=OFF), gr.update(type="pil", value=[img_empty], visible=False))
    ret_on = gr.update(value=ON)
    if switch == ON:
        return ret_off

    size = IMG_NUM_GALLERY
    tag_summary: TagsSummary = pool.tags[tag]
    urls = [pool[i]["img_url"] for i in tag_summary["selection"]]
    return ret_on, (gr.update(type="filepath", value=urls, visible=True))

def switch_gallery_notags(switch: str, tag: str):
    OFF = LABEL_BUTT_GALLERY_OFF_NOTAGS
    ON = LABEL_BUTT_GALLERY_ON_NOTAGS
    ret_off = (gr.update(value=OFF), gr.update(type="pil", value=[img_empty], visible=False))
    ret_on = gr.update(value=ON)
    if switch == ON:
        return ret_off

    size = IMG_NUM_GALLERY
    tag_summary: TagsSummary = pool.tags[tag]
    s_diff = pool.selection.clone_empty
    s_diff.all
    s_diff -= tag_summary["selection"]
    urls = [pool[i]["img_url"] for i in s_diff]
    return ret_on, (gr.update(type="filepath", value=urls, visible=True))

def update_tags(page: int):
    tags = pool.tags_ordered
    size = TAG_NUM_PER_PAGE
    start = (page-1) * size
    end = start + size

    if start >= len(tags):
        gr.Warning("Tags size overflow!")
        return gr.skip()
    if end > len(tags):
        end = len(tags)
    tags = tags[start:end]

    update = []
    for i, tag in enumerate(tags):
        tags_summary: TagsSummary = pool.tags[tag] 
        update.append(gr.update(value=tag, label=f"Tag [size: {len(tags_summary['selection'])}]"))
    for j in range(i+1, TAG_NUM_PER_PAGE):
        update.append(gr.update(value="", label="Tag"))
    
    return update

def store_action(tag: str, action: Literal["delete", "replace", "deselect", "deselect_notags", "no_action", "undef"], payload: str):
    tag_summary: TagsSummary = pool.tags[tag]
    tag_summary["action"]["action"] = action
    tag_summary["action"]["payload"] = payload
    pool.tags[tag] = tag_summary

def restore_actions(tags: dict):
    update = []
    for tag in tags.values():
        tag_summary: TagsSummary = pool.tags[tag]
        value = tag_summary["action"]["action"]
        update.append(gr.update(value=value))
    return update

def restore_payloads(tags: dict):
    update = []
    for tag in tags.values():
        tag_summary: TagsSummary = pool.tags[tag]
        value = tag_summary["action"]["payload"]
        update.append(gr.update(value=value))
    return update

def build_tags(trigger: str):
    gr.Info("Building tags ...")
    pool.build_tags_train(trigger)
    pool.safe_tags_train
    gr.Info("Building done!")

with gr.Blocks() as interface:
    #gr.Markdown("Template")
    with gr.Row():
        labels = ["None"] + pools.labels
        pools_select = gr.Dropdown(labels, label="Choose Pool", multiselect=False, value=labels[0],scale=2, interactive=True)
        page_select = gr.Dropdown([1], label= "Page", multiselect=False, value=1, scale=2, interactive=True)
        trigger = gr.Textbox(placeholder="Enter trigger tag", label="Trigger Tag", scale=2, interactive=True)
        btn_do_caption = gr.Button("Build Tags", scale=1)

    rows = []
    for i in range(TAG_NUM_PER_PAGE):
        with gr.Row(visible=False,show_progress=True) as row:
            rows.append(row)
            rows_tag[i].render()
            with gr.Column(scale=1):
                rows_payload[i].render()
                rows_action[i].render()
            with gr.Column(scale=2):
                with gr.Group():
                    rows_butt_galleries[i].render()
                    rows_butt_galleries_notags[i].render()
                    rows_galleries[i].render()

        rows_action[i].change(store_action, [rows_tag[i], rows_action[i], rows_payload[i]], None)     
                
        rows_butt_galleries[i].click(switch_gallery, [rows_butt_galleries[i] ,rows_tag[i]], [rows_butt_galleries[i], rows_galleries[i]])
        rows_butt_galleries_notags[i].click(switch_gallery_notags, [rows_butt_galleries_notags[i] ,rows_tag[i]], [rows_butt_galleries_notags[i], rows_galleries[i]])
    
    pools_select.change(hide_groups,None, rows) \
        .then(flush_tags,None, rows_tag) \
        .then(new_pool,pools_select, None) \
        .then(new_pool_page, pools_select, page_select) \
        .then(update_tags, page_select, rows_tag) \
        .then(restore_actions, rows_tag_seq, rows_action) \
        .then(restore_payloads, rows_tag_seq, rows_payload) \
        .then(show_groups,page_select,rows)
    page_select.change(update_tags,page_select, rows_tag) \
        .then(restore_actions, rows_tag_seq, rows_action) \
        .then(restore_payloads, rows_tag_seq, rows_payload)
    
    btn_do_caption.click(build_tags, trigger, None)
