import gradio as gr
with gr.Blocks() as demo:
	gr.HTML("EMPTY APP")
	with gr.Row():
			run_button = gr.Button("Submit Empty")
if __name__ == "__main__":
    demo.launch()

