import gradio as gr

#def _greet(name, intensity):
#    return "Hello, " + name + "!" * int(intensity)
#
#interface = gr.Interface(
#    #title="Template",
#    fn=_greet,
#    inputs=["text", "slider"],
#    outputs=["text"],
#)

with gr.Blocks() as interface:
    gr.Markdown("Template")
    with gr.Row():
        inp_row = gr.Textbox(value="depp", label="Sepp")