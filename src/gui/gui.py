import tkinter as tk
from PIL import Image, ImageTk

from ..imgset import ImgSet

def gui(pool_name: str, count: int):
    root = tk.Tk()
    root.title("ImgSet Image Tagger")
    label = tk.Label(root, text ="Hello World !").pack()
    root.mainloop() 

    #image = Image.open(image_path)
    #photo = ImageTk.PhotoImage(image)

    #label = tk.Label(root, image = photo)
    #label.image = photo
    #label.grid(row=1)
