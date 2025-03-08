import gradio as gr

from label import interface as label_interface
from config import interface as config_interface
from tag import interface as tag_interface
from template import interface as template_interface

app = gr.TabbedInterface([label_interface,tag_interface,config_interface,template_interface], ["Label","Tag","Config","Template"])

app.launch()

#from PIL import Image
#from PIL.PngImagePlugin import PngInfo
#
#targetImage = Image.open("pathToImage.png")
#
#metadata = PngInfo()
#metadata.add_text("MyNewString", "A string")
#metadata.add_text("MyNewInt", str(1234))
#
#targetImage.save("NewPath.png", pnginfo=metadata)
#targetImage = Image.open("NewPath.png")
#
#print(targetImage.text)
#
#>>> {'MyNewString': 'A string', 'MyNewInt': '1234'}


