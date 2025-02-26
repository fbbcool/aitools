import gradio as gr

from label import interface as label_interface
from config import interface as config_interface
from template import interface as template_interface

app = gr.TabbedInterface([label_interface,config_interface,template_interface], ["Label","Config","Template"])

app.launch()


