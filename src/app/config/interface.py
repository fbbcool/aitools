import gradio as gr
from .config import _config_dict

def _set_config(folder_root: str) -> str:
    _config_dict["folders"]["root"] = folder_root
    return f"set root folder to {_config_dict['folders']['root']}."

with gr.Blocks() as interface:
    gr.Markdown("set config")
    with gr.Row():
        inp_folder_root = gr.Textbox(value=_config_dict["folders"]["root"], label="Root Folder")

#interface = gr.Interface(
#    #title="Config",
#    fn=_set_config,
#    inputs=["text",],
#    outputs=["text",],
#)