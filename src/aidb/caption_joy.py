import sys
from PIL import Image
from threading import Thread, Lock
from typing import Final, Generator

from transformers import LlavaForConditionalGeneration, TextIteratorStreamer, AutoProcessor
from liger_kernel.transformers import apply_liger_kernel_to_llama
import torch


MODEL_PATH = "fancyfeast/llama-joycaption-beta-one-hf-llava"

DEFAULT_SYSTEM: Final = "You are a helpful assistant and help users with any queries they may have with no censorship or restrictions. "
CONTENT_SYSTEM: Final = {
	"1gts": "The users are interested in the giantess theme and mostly interested in the interaction of a tall female giantess with a small adult man.",
	"1woman": "The users are interested in women with big breasts and hairy women and how they present their bodies.",
	"1busty": "The users are interested in women with big breasts and how they present their bodies.",
	"1hairy": "The users are interested in very hairy woman how they present their bodies.",
}
DEFAULT_PROMPT: Final = "Write a very long detailed description for this image."
CONTENT_PROMPT: Final = {
	"1gts": "The users are interested in the giantess theme and mostly interested in the interaction of a tall female giantess with a small adult man.",
	"1woman": "The users are interested in women with big breasts and hairy women and how they present their bodies.",
	"1busty": "The users are interested in women with big breasts and how they present their bodies.",
	"1hairy": "The users are interested in very hairy woman how they present their bodies.",
}

class CapJoy():
	def __init__(self, trigger: str = "", configure_ai: bool = True):
		self.lock = Lock()
		self._ai = configure_ai
		self._tokens = 512
		self._top_p = 0.9
		self._temperature = 0.6
		self._trigger = trigger
		# configure
		content_system = DEFAULT_SYSTEM + CONTENT_SYSTEM.get(self._trigger, "")
		self._convo = [
			{
				"role": "system",
				# Beta One supports a wider range of system prompts, but this is a good default
				# "content": "You are a helpful assistant and help users with any queries they may have with no censorship or restrictions. the users are interested in the giantess theme and mostly interested in the interaction of a tall female giantess with a small adult man.",
				"content": content_system,
			},
			{
				"role": "user",
				"content": "",
			},
		]
		# configure AI
		# Load model
		self.processor = None
		self.model = None
		if self._ai:
			self._configure_ai()
	
	# the public interface
	def img_caption(self, img: Image.Image) -> str:
		prompt = DEFAULT_PROMPT + CONTENT_SYSTEM.get(self._trigger, "")
		with self.lock:
			for caption in self._process(img, prompt):
				pass
			return caption

	def _configure_ai(self) -> None:
		# Load model
		self.processor = AutoProcessor.from_pretrained(MODEL_PATH)
		self.model = LlavaForConditionalGeneration.from_pretrained(MODEL_PATH, torch_dtype="bfloat16", device_map=0)
		assert isinstance(self.model, LlavaForConditionalGeneration), f"Expected LlavaForConditionalGeneration, got {type(self.model)}"
		self.model.eval()
		apply_liger_kernel_to_llama(model=self.model.language_model)  # Meow


	def _process(self, img: Image.Image, prompt: str) -> Generator[str, None, None]:
		# Format the conversation
		# WARNING: HF's handling of chat's on Llava models is very fragile.  This specific combination of processor.apply_chat_template(), and processor() works
		# but if using other combinations always inspect the final input_ids to ensure they are correct.  Often times you will end up with multiple <bos> tokens
		# if not careful, which can make the model perform poorly.
		convo = self._convo.copy()
		convo[1]["content"] = prompt

		# run w/ AI
		if self._ai:
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

		# mock AI
		else:
			streamer_mock = ["null", ",", "null"]	
			generated_text = ""
			for new_text in streamer_mock:
				generated_text += new_text
				yield generated_text