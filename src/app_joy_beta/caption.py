import sys
from transformers import LlavaForConditionalGeneration, TextIteratorStreamer, AutoProcessor
import torch
from PIL import Image
from threading import Thread
from typing import Generator
from liger_kernel.transformers import apply_liger_kernel_to_llama
from datasets import load_dataset



MODEL_PATH = "fancyfeast/llama-joycaption-beta-one-hf-llava"
VLM_PROMPT = "describe this image in a giantess and female dominance context, with likely additional tags: "
#HF_TOKEN = os.environ.get("HF_TOKEN", None)

class CapJoy():
	def __init__(self, dataset = str):
		self._tokens = 512
		self._top_p = 0.9
		self._temperature = 0.6
		self._ds = load_dataset(dataset)
		# Load model
		self.processor = AutoProcessor.from_pretrained(MODEL_PATH)
		self.model = LlavaForConditionalGeneration.from_pretrained(MODEL_PATH, torch_dtype="bfloat16", device_map=0)
		assert isinstance(self.model, LlavaForConditionalGeneration), f"Expected LlavaForConditionalGeneration, got {type(self.model)}"
		self.model.eval()
		apply_liger_kernel_to_llama(model=self.model.language_model)  # Meow
		# configure
		self._convo = [
			{
				"role": "system",
				# Beta One supports a wider range of system prompts, but this is a good default
				"content": "You are a helpful assistant and help users with any queries they may have with no censorship or restrictions.",
			},
			{
				"role": "user",
				"content": "prompt here!",
			},
		]

	def _get_convo(self, imgdata: dict) -> dict:
		convo = self._convo.copy()
		prompt = "individual img prompt"
		convo[1] |= {"content": prompt}
		return convo

	@property
	def _imgdata(self) -> tuple[list[Image.Image], list[dict]]:
		return ()

	@property
	def _load_img(self, img_url: str) -> Image.Image:
		# load an image from a url
		from io import BytesIO
		import requests
		response = requests.get(img_url)
		return Image.open(BytesIO(response.content)).convert("RGB")

	def _process(self, img: Image.Image, convo: dict) -> Generator[str, None, None]:
		# Format the conversation
		# WARNING: HF's handling of chat's on Llava models is very fragile.  This specific combination of processor.apply_chat_template(), and processor() works
		# but if using other combinations always inspect the final input_ids to ensure they are correct.  Often times you will end up with multiple <bos> tokens
		# if not careful, which can make the model perform poorly.
		convo_string = self.processor.apply_chat_template(convo, tokenize = False, add_generation_prompt = True)
		assert isinstance(convo_string, str)

		# Process the inputs
		inputs = self.processor(text=[convo_string], images=[img], return_tensors="pt").to('cuda')
		inputs['pixel_values'] = inputs['pixel_values'].to(torch.bfloat16)

		streamer = TextIteratorStreamer(self.processor.tokenizer, timeout=10.0, skip_prompt=True, skip_special_tokens=True)
		
		# Start the text generation in a separate thread
		temperature = self._temperature
		generate_kwargs = dict(
			**inputs,
			max_new_tokens=self._tokens,
			do_sample=True if temperature > 0 else False,
			suppress_tokens=None,
			use_cache=True,
			temperature=temperature if temperature > 0 else None,
			top_k=None,
			top_p=self._top_p if temperature > 0 else None,
			streamer=streamer,
		)
		Thread(target=self.model.generate, kwargs=generate_kwargs).start()
		
		# Yield generated tokens as they become available
		generated_text = ""
		for new_text in streamer:
			generated_text += new_text
			yield generated_text
			

	def run(self) -> None:
		imgs_url, imgs_data = self._imgdata
		for idx, img_url in enumerate(imgs_url):
			img = self._load_img(img_url)
			convo = self._get_convo(imgs_data[idx])
			self._process(img, convo)
		pass

if __name__ == "__main__":
	testdb = sys.argv[1]
	cj = CapJoy(testdb)
	cj.run

