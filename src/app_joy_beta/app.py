import gradio as gr
from transformers import LlavaForConditionalGeneration, TextIteratorStreamer, AutoProcessor
import torch
from PIL import Image
from threading import Thread
from typing import Generator
from liger_kernel.transformers import apply_liger_kernel_to_llama




LOGO_SRC = """data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjwhRE9DVFlQRSBzdmcgUFVCTElDICItLy9XM0MvL0RURCBTVkcgMS4xLy9FTiIgImh0dHA6Ly93d3cudzMub3JnL0dyYXBoaWNzL1NWRy8xLjEvRFREL3N2ZzExLmR0ZCI+Cjxzdmcgd2lkdGg9IjEwMCUiIGhlaWdodD0iMTAwJSIgdmlld0JveD0iMCAwIDUzOCA1MzUiIHZlcnNpb249IjEuMSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIiB4bWxuczp4bGluaz0iaHR0cDovL3d3dy53My5vcmcvMTk5OS94bGluayIgeG1sOnNwYWNlPSJwcmVzZXJ2ZSIgeG1sbnM6c2VyaWY9Imh0dHA6Ly93d3cuc2VyaWYuY29tLyIgc3R5bGU9ImZpbGwtcnVsZTpldmVub2RkO2NsaXAtcnVsZTpldmVub2RkO3N0cm9rZS1saW5lam9pbjpyb3VuZDtzdHJva2UtbWl0ZXJsaW1pdDoyOyI+CiAgICA8ZyB0cmFuc2Zvcm09Im1hdHJpeCgxLDAsMCwxLC0xNDcuODcxLDAuMDAxOTA4NjMpIj4KICAgICAgICA8cGF0aCBkPSJNMTk1LjY3LDIyMS42N0MxOTYuNzMsMjA1LjM3IDIwMC4yOCwxODkuNzYgMjA3LjkxLDE3NS4zN0MyMjcuOTgsMTM3LjUxIDI1OS4zMywxMTQuODggMzAyLjAxLDExMS42M0MzMzQuMTUsMTA5LjE4IDM2Ni41OSwxMTAuNiAzOTguODksMTEwLjNDNDAwLjUzLDExMC4yOCA0MDIuMTYsMTEwLjMgNDA0LjQsMTEwLjNDNDA0LjQsMTAxLjk5IDQwNC41Niw5NC4wNSA0MDQuMjMsODYuMTJDNDA0LjE4LDg0Ljg0IDQwMi4xNSw4My4xMyA0MDAuNjYsODIuNDlDMzgzLjIzLDc1LjAyIDM3My4wNSw1OS43OSAzNzMuOTYsNDAuOTZDMzc1LjA5LDE3LjU0IDM5MS40NywyLjY2IDQxMC42NSwwLjM3QzQzNy44OSwtMi44OSA0NTUuNTYsMTUuODQgNDU5LjI2LDM0LjY5QzQ2Mi45Niw1My41NyA0NTIuMTgsNzYuOTMgNDMyLjgxLDgyLjY2QzQzMS42NCw4My4wMSA0MzAuMzMsODUuMjMgNDMwLjI4LDg2LjYyQzQzMC4wMyw5NC4yNiA0MzAuMTYsMTAxLjkyIDQzMC4xNiwxMTAuM0w0MzUuNjMsMTEwLjNDNDYzLjc5LDExMC4zIDQ5MS45NiwxMTAuMjggNTIwLjEyLDExMC4zQzU3NC44NCwxMTAuMzYgNjIzLjA0LDE0OC4zNSA2MzUuNjcsMjAxLjU1QzYzNy4yMywyMDguMTMgNjM3LjgzLDIxNC45MyA2MzguODksMjIxLjY3QzY2MC40MywyMjQuOTQgNjc1LjE5LDIzNi42MiA2ODIuMzYsMjU3LjRDNjgzLjU5LDI2MC45NyA2ODQuNjUsMjY0LjgyIDY4NC42NywyNjguNTRDNjg0Ljc3LDI4My4zNCA2ODUuNzYsMjk4LjMxIDY4My45NCwzMTIuOTFDNjgwLjg5LDMzNy4yOSA2NjIuODYsMzUzLjM2IDYzOC40NywzNTUuODJDNjM1LjE0LDM4NS4wOCA2MjEuOTEsNDA5LjQxIDYwMC40NSw0MjkuMjFDNTgxLjYsNDQ2LjYxIDU1OS4xNCw0NTcuNSA1MzMuNTcsNDU5LjE4QzUwOC4xOCw0NjAuODQgNDgyLjY0LDQ2MC4yIDQ1Ny4xNiw0NjAuMzhDNDM1LjE2LDQ2MC41MyA0MTMuMTcsNDYwLjM0IDM5MS4xNyw0NjAuNTNDMzg4Ljc2LDQ2MC41NSAzODUuOTUsNDYxLjU2IDM4NC4wMyw0NjMuMDRDMzcxLjU0LDQ3Mi42MiAzNTkuMTMsNDgyLjMxIDM0Ni45Miw0OTIuMjVDMzM4Ljk0LDQ5OC43NSAzMzEuMzksNTA1Ljc3IDMyMy41Niw1MTIuNDZDMzE3LjQ1LDUxNy42OCAzMTAuOTMsNTIyLjQ0IDMwNS4xMSw1MjcuOTVDMzAxLjE5LDUzMS42NiAyOTYuNTIsNTMzLjE3IDI5MS42OSw1MzQuMzZDMjg1LjY1LDUzNS44NSAyNzkuMjIsNTI5LjEzIDI3OS4wMSw1MjEuMTlDMjc4LjgsNTEyLjg2IDI3OC45NSw1MDQuNTMgMjc4Ljk0LDQ5Ni4xOUwyNzguOTQsNDU2LjY5QzIzMi44Miw0MzguMTYgMjAzLjU2LDQwNi4yMyAxOTUuMDcsMzU2LjA4QzE5My4yNiwzNTUuNzUgMTkwLjg0LDM1NS40MSAxODguNDgsMzU0Ljg2QzE2Ny40NiwzNDkuOTEgMTU1LjA0LDMzNi4wMiAxNTAuNzIsMzE1LjYyQzE0Ni45OCwyOTcuOTkgMTQ2LjksMjc5LjY3IDE1MC42MSwyNjIuMDlDMTU1LjU1LDIzOC42OCAxNzEuNDIsMjI1LjU5IDE5NS42NiwyMjEuNjdMMTk1LjY3LDIyMS42N1pNMzA4LjA3LDQ4Ny44MkMzMTUuOTQsNDgxLjEzIDMyMi44NSw0NzUuMTMgMzI5LjksNDY5LjNDMzQ0LjM5LDQ1Ny4zMSAzNTguOSw0NDUuMzYgMzczLjU0LDQzMy41NkMzNzUuMTcsNDMyLjI1IDM3Ny42OCw0MzEuNCAzNzkuNzksNDMxLjM5QzQxNC43OCw0MzEuMjYgNDQ5Ljc4LDQzMS4zOCA0ODQuNzcsNDMxLjI0QzUwMC4zOSw0MzEuMTggNTE2LjEzLDQzMS43NiA1MzEuNjIsNDMwLjE2QzU3Ni45Miw0MjUuNDkgNjA5LjI0LDM4Ny43NyA2MDguOTUsMzQ0Ljg0QzYwOC42OCwzMDUuNTIgNjA4LjkzLDI2Ni4xOSA2MDguODcsMjI2Ljg2QzYwOC44NywyMjMuMjIgNjA4LjU4LDIxOS41NSA2MDcuOTksMjE1Ljk2QzYwMy4xMSwxODYuMjkgNTg4LjYxLDE2My4zMyA1NjEuMzIsMTQ5LjMyQzU0OS4wNCwxNDMuMDIgNTM2LjE1LDEzOS4yOSA1MjIuMjIsMTM5LjI5QzQ1My45LDEzOS4zMiAzODUuNTgsMTM5LjIgMzE3LjI2LDEzOS4zNUMzMDkuMiwxMzkuMzcgMzAwLjk2LDEzOS44OSAyOTMuMTEsMTQxLjZDMjU0LjE5LDE1MC4wNyAyMjUuMzMsMTg1LjY5IDIyNS4wMywyMjUuNDJDMjI0LjgsMjU2LjA4IDIyNC44NiwyODYuNzQgMjI0Ljk5LDMxNy40QzIyNS4wNSwzMzAuNTMgMjI0Ljc0LDM0My43NiAyMjYuMTgsMzU2Ljc3QzIyOC43NCwzODAuMDUgMjQwLjYsMzk4LjYyIDI1OC43OSw0MTIuOTNDMjczLjA0LDQyNC4xNCAyODkuNjMsNDMwLjAyIDMwNy42MSw0MzEuNTVDMzA3LjgyLDQzMi4wMyAzMDguMDYsNDMyLjMzIDMwOC4wNiw0MzIuNjNDMzA4LjA4LDQ1MC42IDMwOC4wOCw0NjguNTcgMzA4LjA4LDQ4Ny44MUwzMDguMDcsNDg3LjgyWk00MzUuNzksNDMuMzNDNDM1Ljk1LDMzLjQyIDQyNy42MSwyNC42NSA0MTcuOCwyNC40QzQwNi43NiwyNC4xMiAzOTguMjUsMzIuMDUgMzk4LjEzLDQyLjc0QzM5OC4wMSw1My4wNCA0MDYuNiw2Mi4xMiA0MTYuNDIsNjIuMDhDNDI3LjExLDYyLjA0IDQzNS42MSw1My44MSA0MzUuNzgsNDMuMzNMNDM1Ljc5LDQzLjMzWiIgc3R5bGU9ImZpbGw6cmdiKDczLDQ3LDExOCk7ZmlsbC1ydWxlOm5vbnplcm87Ii8+CiAgICAgICAgPHBhdGggZD0iTTQxOS4zLDM5MS42M0MzNzQuNDYsMzkwLjQgMzQxLjUxLDM3Mi42MyAzMTguMDEsMzM3LjcxQzMxNS42NywzMzQuMjMgMzEzLjc3LDMzMC4wNCAzMTMuMSwzMjUuOTVDMzExLjg0LDMxOC4yOCAzMTYuNTMsMzExLjcgMzIzLjcyLDMwOS40NkMzMzAuNjYsMzA3LjI5IDMzOC4zMiwzMTAuMSAzNDEuOTgsMzE3LjAzQzM0OS4xNSwzMzAuNjMgMzU5LjE2LDM0MS4zNSAzNzIuMywzNDkuMzFDNDAxLjMyLDM2Ni44OSA0NDQuNTYsMzYzLjcgNDcwLjYxLDM0Mi4zNUM0NzkuMSwzMzUuMzkgNDg2LjA4LDMyNy40MSA0OTEuNTUsMzE3Ljk3QzQ5NS4wNSwzMTEuOTMgNTAwLjIsMzA4LjE4IDUwNy40NywzMDguOTVDNTEzLjczLDMwOS42MSA1MTguODYsMzEyLjg4IDUyMC4xMiwzMTkuMjFDNTIwLjksMzIzLjEzIDUyMC43MywzMjguMjIgNTE4LjgzLDMzMS41NUM1MDAuNjMsMzYzLjMyIDQ3My41NSwzODIuOTUgNDM3LjI5LDM4OS4zN0M0MzAuNDQsMzkwLjU4IDQyMy40OCwzOTEuMTIgNDE5LjI5LDM5MS42M0w0MTkuMywzOTEuNjNaIiBzdHlsZT0iZmlsbDpyZ2IoMjUwLDEzOSwxKTtmaWxsLXJ1bGU6bm9uemVybzsiLz4KICAgICAgICA8cGF0aCBkPSJNNDYyLjcxLDI0MC4xOUM0NjIuOCwyMTYuOTEgNDgwLjI0LDE5OS43OSA1MDQuMDEsMTk5LjY3QzUyNi41NywxOTkuNTUgNTQ0Ljg5LDIxOC4wNyA1NDQuNTEsMjQxLjM0QzU0NC4xOCwyNjEuODUgNTMwLjA5LDI4MS45NiA1MDEuOTEsMjgxLjIzQzQ4MC42OCwyODAuNjggNDYyLjE1LDI2My44IDQ2Mi43MSwyNDAuMkw0NjIuNzEsMjQwLjE5WiIgc3R5bGU9ImZpbGw6cmdiKDI1MCwxMzksMSk7ZmlsbC1ydWxlOm5vbnplcm87Ii8+CiAgICAgICAgPHBhdGggZD0iTTM3MC45OSwyNDAuMDhDMzcxLDI2Mi43OSAzNTIuNTMsMjgxLjM1IDMyOS44OSwyODEuMzdDMzA3LjA1LDI4MS40IDI4OC45NiwyNjMuNDIgMjg4Ljk2LDI0MC42OEMyODguOTYsMjE4LjE0IDMwNi43MywyMDAgMzI5LjE2LDE5OS42MkMzNTIuMDIsMTk5LjI0IDM3MC45OCwyMTcuNTcgMzcwLjk5LDI0MC4wOFoiIHN0eWxlPSJmaWxsOnJnYigyNTAsMTM5LDEpO2ZpbGwtcnVsZTpub256ZXJvOyIvPgogICAgPC9nPgo8L3N2Zz4K"""

MODEL_PATH = "fancyfeast/llama-joycaption-beta-one-hf-llava"
TITLE = f"""<style>
  .joy-header   {{display:flex; align-items:center; justify-content:center;
                 gap:16px; margin:4px 0 12px;}}
  .joy-header h1{{margin:0; font-size:1.9rem; line-height:1.2;}}
  .joy-header p {{margin:2px 0 0; font-size:0.9rem; color:#666;}}
  .joy-header img{{height:56px;}}
</style>
<div class="joy-header">
  <img src="{LOGO_SRC}" alt="JoyCaption logo">
  <div>
    <h1>JoyCaption <span style="font-weight:400">Beta&nbsp;One</span></h1>
    <p>Image-captioning model &nbsp;|&nbsp; build mb3500zp</p>
  </div>
</div>
<hr>"""
DESCRIPTION = """
<div>
<h2>Quick-start</h2>
<ol>
  <li><strong>Upload or drop</strong> an image in the left-hand panel.</li>
  <li>Pick a <strong>Caption Type</strong> and, if you wish, adjust the <strong>Caption Length</strong>.</li>
  <li>(Optional) <em>expand the "Extra Options" accordion</em> and tick any boxes that should influence the caption.</li>
  <li>(Optional) open <em>Generation settings</em> to adjust <code>temperature</code>, <code>top-p</code>, or <code>max&nbsp;tokens</code>.</li>
  <li>Press <kbd>Caption</kbd>.  
      The prompt sent to the model appears in the <em>Prompt</em> box (editable),  
      and the resulting caption streams into the <em>Caption</em> box.</li>
</ol>
<!-- ───────────────────── Caption-type reference ──────────────────── -->
<h2>Caption Types</h2>
<table>
  <tr><th>Mode</th><th>What it does</th></tr>
  <tr><td><strong>Descriptive</strong></td>
      <td>Formal, detailed prose description.</td></tr>
  <tr><td><strong>Descriptive&nbsp;(Casual)</strong></td>
      <td>Similar to Descriptive but with a friendlier, conversational tone.</td></tr>
  <tr><td><strong>Straightforward</strong></td>
      <td>Objective, no fluff, and more succinct than Descriptive.</td></tr>
  <tr><td><strong>Stable Diffusion Prompt</strong></td>
      <td>Reverse-engineers a prompt that could have produced the image in a SD/T2I model.<br><em>⚠︎ Experimental – can glitch ≈ 3% of the time.</em></td></tr>
  <tr><td><strong>MidJourney</strong></td>
      <td>Same idea as above but tuned to MidJourney’s prompt style.<br><em>⚠︎ Experimental – can glitch ≈ 3% of the time.</em></td></tr>
  <tr><td><strong>Danbooru tag list</strong></td>
      <td>Comma-separated tags strictly following Danbooru conventions
          (artist:, copyright:, etc.). Lower-case underscores only.<br><em>⚠︎ Experimental – can glitch ≈ 3% of the time.</em></td></tr>
  <tr><td><strong>e621 tag list</strong></td>
      <td>Alphabetical, namespaced tags in e621 style – includes species/meta
          tags when relevant.<br><em>⚠︎ Experimental – can glitch ≈ 3% of the time.</em></td></tr>
  <tr><td><strong>Rule34 tag list</strong></td>
      <td>Rule34 style alphabetical tag dump; artist/copyright/character
          prefixes first.<br><em>⚠︎ Experimental – can glitch ≈ 3% of the time.</em></td></tr>
  <tr><td><strong>Booru-like tag list</strong></td>
      <td>Looser tag list when you want labels but not a specific Booru format.<br><em>⚠︎ Experimental – can glitch ≈ 3% of the time.</em></td></tr>
  <tr><td><strong>Art Critic</strong></td>
      <td>Paragraph of art-historical commentary: composition, symbolism, style,
          lighting, movement, etc.</td></tr>
  <tr><td><strong>Product Listing</strong></td>
      <td>Short marketing copy as if selling the depicted object.</td></tr>
  <tr><td><strong>Social Media Post</strong></td>
      <td>Catchy caption aimed at platforms like Instagram or BlueSky.</td></tr>
</table>
<p style="margin-top:0.6em">
  <strong>Note&nbsp;on Booru modes:</strong> They’re tuned for
  anime-style / illustration imagery; accuracy drops on real-world photographs
  or highly abstract artwork.
</p>
<!-- ───────────────────── Extras + generation notes ───────────────── -->
<h3>Extra Options</h3>
<p>These check-boxes fine-tune what the model should or should not mention:
lighting, camera angle, aesthetic rating, profanity, etc.  
Toggle them before hitting <kbd>Caption</kbd>; the prompt box will update
instantly.</p>
<h3>Generation settings</h3>
<ul>
  <li><strong>Temperature</strong> – randomness.  
      0&nbsp;=&nbsp;deterministic; higher =&nbsp;more variety.</li>
  <li><strong>Top-p</strong> – nucleus sampling cutoff. Lower =&nbsp;safer,
      higher =&nbsp;freer.</li>
  <li><strong>Max&nbsp;New Tokens</strong> – hard stop for the model’s output length.</li>
</ul>
<p>Enjoy experimenting, and feel free to open an issue if you
spot any bugs or have feature ideas!</p>
<hr>
<p>🚨🚨🚨 If the "Help improve JoyCaption" box is checked, the _text_ query you write will be logged and I _might_ use it to help improve JoyCaption.
It does not log images, user data, etc; only the text query.  I cannot see what images you send, and frankly, I don't want to.  But knowing what kinds of instructions
and queries users want JoyCaption to handle will help guide me in building JoyCaption's dataset.  This dataset will be made public.  As always, the model itself is completely
public and free to use outside of this space.  And, of course, I have no control nor access to what HuggingFace, which are graciously hosting this space, collects.</p>
</div>
"""

CAPTION_TYPE_MAP = {
	"Descriptive": [
		"Write a detailed description for this image.",
		"Write a detailed description for this image in {word_count} words or less.",
		"Write a {length} detailed description for this image.",
	],
	"Descriptive (Casual)": [
		"Write a descriptive caption for this image in a casual tone.",
		"Write a descriptive caption for this image in a casual tone within {word_count} words.",
		"Write a {length} descriptive caption for this image in a casual tone.",
	],
	"Straightforward": [
		"Write a straightforward caption for this image. Begin with the main subject and medium. Mention pivotal elements—people, objects, scenery—using confident, definite language. Focus on concrete details like color, shape, texture, and spatial relationships. Show how elements interact. Omit mood and speculative wording. If text is present, quote it exactly. Note any watermarks, signatures, or compression artifacts. Never mention what's absent, resolution, or unobservable details. Vary your sentence structure and keep the description concise, without starting with “This image is…” or similar phrasing.",
		"Write a straightforward caption for this image within {word_count} words. Begin with the main subject and medium. Mention pivotal elements—people, objects, scenery—using confident, definite language. Focus on concrete details like color, shape, texture, and spatial relationships. Show how elements interact. Omit mood and speculative wording. If text is present, quote it exactly. Note any watermarks, signatures, or compression artifacts. Never mention what's absent, resolution, or unobservable details. Vary your sentence structure and keep the description concise, without starting with “This image is…” or similar phrasing.",
		"Write a {length} straightforward caption for this image. Begin with the main subject and medium. Mention pivotal elements—people, objects, scenery—using confident, definite language. Focus on concrete details like color, shape, texture, and spatial relationships. Show how elements interact. Omit mood and speculative wording. If text is present, quote it exactly. Note any watermarks, signatures, or compression artifacts. Never mention what's absent, resolution, or unobservable details. Vary your sentence structure and keep the description concise, without starting with “This image is…” or similar phrasing.",
	],
	"Stable Diffusion Prompt": [
		"Output a stable diffusion prompt that is indistinguishable from a real stable diffusion prompt.",
		"Output a stable diffusion prompt that is indistinguishable from a real stable diffusion prompt. {word_count} words or less.",
		"Output a {length} stable diffusion prompt that is indistinguishable from a real stable diffusion prompt.",
	],
	"MidJourney": [
		"Write a MidJourney prompt for this image.",
		"Write a MidJourney prompt for this image within {word_count} words.",
		"Write a {length} MidJourney prompt for this image.",
	],
	"Danbooru tag list": [
		"Generate only comma-separated Danbooru tags (lowercase_underscores). Strict order: `artist:`, `copyright:`, `character:`, `meta:`, then general tags. Include counts (1girl), appearance, clothing, accessories, pose, expression, actions, background. Use precise Danbooru syntax. No extra text.",
		"Generate only comma-separated Danbooru tags (lowercase_underscores). Strict order: `artist:`, `copyright:`, `character:`, `meta:`, then general tags. Include counts (1girl), appearance, clothing, accessories, pose, expression, actions, background. Use precise Danbooru syntax. No extra text. {word_count} words or less.",
		"Generate only comma-separated Danbooru tags (lowercase_underscores). Strict order: `artist:`, `copyright:`, `character:`, `meta:`, then general tags. Include counts (1girl), appearance, clothing, accessories, pose, expression, actions, background. Use precise Danbooru syntax. No extra text. {length} length.",
	],
	"e621 tag list": [
		"Write a comma-separated list of e621 tags in alphabetical order for this image. Start with the artist, copyright, character, species, meta, and lore tags (if any), prefixed by 'artist:', 'copyright:', 'character:', 'species:', 'meta:', and 'lore:'. Then all the general tags.",
		"Write a comma-separated list of e621 tags in alphabetical order for this image. Start with the artist, copyright, character, species, meta, and lore tags (if any), prefixed by 'artist:', 'copyright:', 'character:', 'species:', 'meta:', and 'lore:'. Then all the general tags. Keep it under {word_count} words.",
		"Write a {length} comma-separated list of e621 tags in alphabetical order for this image. Start with the artist, copyright, character, species, meta, and lore tags (if any), prefixed by 'artist:', 'copyright:', 'character:', 'species:', 'meta:', and 'lore:'. Then all the general tags.",
	],
	"Rule34 tag list": [
		"Write a comma-separated list of rule34 tags in alphabetical order for this image. Start with the artist, copyright, character, and meta tags (if any), prefixed by 'artist:', 'copyright:', 'character:', and 'meta:'. Then all the general tags.",
		"Write a comma-separated list of rule34 tags in alphabetical order for this image. Start with the artist, copyright, character, and meta tags (if any), prefixed by 'artist:', 'copyright:', 'character:', and 'meta:'. Then all the general tags. Keep it under {word_count} words.",
		"Write a {length} comma-separated list of rule34 tags in alphabetical order for this image. Start with the artist, copyright, character, and meta tags (if any), prefixed by 'artist:', 'copyright:', 'character:', and 'meta:'. Then all the general tags.",
	],
	"Booru-like tag list": [
		"Write a list of Booru-like tags for this image.",
		"Write a list of Booru-like tags for this image within {word_count} words.",
		"Write a {length} list of Booru-like tags for this image.",
	],
	"Art Critic": [
		"Analyze this image like an art critic would with information about its composition, style, symbolism, the use of color, light, any artistic movement it might belong to, etc.",
		"Analyze this image like an art critic would with information about its composition, style, symbolism, the use of color, light, any artistic movement it might belong to, etc. Keep it within {word_count} words.",
		"Analyze this image like an art critic would with information about its composition, style, symbolism, the use of color, light, any artistic movement it might belong to, etc. Keep it {length}.",
	],
	"Product Listing": [
		"Write a caption for this image as though it were a product listing.",
		"Write a caption for this image as though it were a product listing. Keep it under {word_count} words.",
		"Write a {length} caption for this image as though it were a product listing.",
	],
	"Social Media Post": [
		"Write a caption for this image as if it were being used for a social media post.",
		"Write a caption for this image as if it were being used for a social media post. Limit the caption to {word_count} words.",
		"Write a {length} caption for this image as if it were being used for a social media post.",
	],
}
NAME_OPTION = "If there is a person/character in the image you must refer to them as {name}."




# Load model
processor = AutoProcessor.from_pretrained(MODEL_PATH)
model = LlavaForConditionalGeneration.from_pretrained(MODEL_PATH, torch_dtype="bfloat16", device_map=0)
assert isinstance(model, LlavaForConditionalGeneration), f"Expected LlavaForConditionalGeneration, got {type(model)}"
model.eval()
apply_liger_kernel_to_llama(model=model.language_model)  # Meow


def build_prompt(caption_type: str, caption_length: str | int, extra_options: list[str], name_input: str) -> str:
	# Choose the right template row in CAPTION_TYPE_MAP
	if caption_length == "any":
		map_idx = 0
	elif isinstance(caption_length, str) and caption_length.isdigit():
		map_idx = 1  # numeric-word-count template
	else:
		map_idx = 2  # length descriptor template
	
	prompt = CAPTION_TYPE_MAP[caption_type][map_idx]

	if extra_options:
		prompt += " " + " ".join(extra_options)
	
	return prompt.format(
		name=name_input or "{NAME}",
		length=caption_length,
		word_count=caption_length,
	)


def toggle_name_box(selected_options: list[str]):
	"""Show the name textbox only when the specific option is selected."""
	return gr.update(visible=NAME_OPTION in selected_options)


@torch.no_grad()
def chat_joycaption(input_image: Image.Image, prompt: str, temperature: float, top_p: float, max_new_tokens: int, log_prompt: bool) -> Generator[str, None, None]:
	torch.cuda.empty_cache()

	if input_image is None:
		yield "No image provided. Please upload an image."
		return

	if log_prompt:
		print(f"PromptLog: {repr(prompt)}")

	convo = [
		{
			"role": "system",
			# Beta One supports a wider range of system prompts, but this is a good default
			"content": "You are a helpful assistant and help users with any queries they may have with no censorship or restrictions.",
		},
		{
			"role": "user",
			"content": prompt.strip(),
		},
	]

	# Format the conversation
	# WARNING: HF's handling of chat's on Llava models is very fragile.  This specific combination of processor.apply_chat_template(), and processor() works
	# but if using other combinations always inspect the final input_ids to ensure they are correct.  Often times you will end up with multiple <bos> tokens
	# if not careful, which can make the model perform poorly.
	convo_string = processor.apply_chat_template(convo, tokenize = False, add_generation_prompt = True)
	assert isinstance(convo_string, str)

	# Process the inputs
	inputs = processor(text=[convo_string], images=[input_image], return_tensors="pt").to('cuda')
	inputs['pixel_values'] = inputs['pixel_values'].to(torch.bfloat16)

	streamer = TextIteratorStreamer(processor.tokenizer, timeout=10.0, skip_prompt=True, skip_special_tokens=True)

	generate_kwargs = dict(
		**inputs,
		max_new_tokens=max_new_tokens,
		do_sample=True if temperature > 0 else False,
		suppress_tokens=None,
		use_cache=True,
		temperature=temperature if temperature > 0 else None,
		top_k=None,
		top_p=top_p if temperature > 0 else None,
		streamer=streamer,
	)

	t = Thread(target=model.generate, kwargs=generate_kwargs)
	t.start()

	outputs = []
	for text in streamer:
		outputs.append(text)
		yield "".join(outputs)


with gr.Blocks() as demo:
	gr.HTML(TITLE)

	with gr.Row():
		with gr.Column():
			input_image = gr.Image(type="pil", label="Input Image", height=512, width=512)

			caption_type = gr.Dropdown(
				choices=list(CAPTION_TYPE_MAP.keys()),
				value="Descriptive",
				label="Caption Type",
			)

			caption_length = gr.Dropdown(
				choices=["any", "very short", "short", "medium-length", "long", "very long"] +
						[str(i) for i in range(20, 261, 10)],
				label="Caption Length",
				value="long",
			)

			with gr.Accordion("Extra Options", open=False):
				extra_options = gr.CheckboxGroup(
					choices=[
						NAME_OPTION,
						"Do NOT include information about people/characters that cannot be changed (like ethnicity, gender, etc), but do still include changeable attributes (like hair style).",
						"Include information about lighting.",
						"Include information about camera angle.",
						"Include information about whether there is a watermark or not.",
						"Include information about whether there are JPEG artifacts or not.",
						"If it is a photo you MUST include information about what camera was likely used and details such as aperture, shutter speed, ISO, etc.",
						"Do NOT include anything sexual; keep it PG.",
						"Do NOT mention the image's resolution.",
						"You MUST include information about the subjective aesthetic quality of the image from low to very high.",
						"Include information on the image's composition style, such as leading lines, rule of thirds, or symmetry.",
						"Do NOT mention any text that is in the image.",
						"Specify the depth of field and whether the background is in focus or blurred.",
						"If applicable, mention the likely use of artificial or natural lighting sources.",
						"Do NOT use any ambiguous language.",
						"Include whether the image is sfw, suggestive, or nsfw.",
						"ONLY describe the most important elements of the image.",
						"If it is a work of art, do not include the artist's name or the title of the work.",
						"Identify the image orientation (portrait, landscape, or square) and aspect ratio if obvious.",
						"""Use vulgar slang and profanity, such as (but not limited to) "fucking," "slut," "cock," etc.""",
						"Do NOT use polite euphemisms—lean into blunt, casual phrasing.",
						"Include information about the ages of any people/characters when applicable.",
						"Mention whether the image depicts an extreme close-up, close-up, medium close-up, medium shot, cowboy shot, medium wide shot, wide shot, or extreme wide shot.",
						"Do not mention the mood/feeling/etc of the image.",
						"Explicitly specify the vantage height (eye-level, low-angle worm’s-eye, bird’s-eye, drone, rooftop, etc.).",
						"If there is a watermark, you must mention it.",
						"""Your response will be used by a text-to-image model, so avoid useless meta phrases like “This image shows…”, "You are looking at...", etc.""",
					],
					label="Select one or more",
				)
			
			name_input = gr.Textbox(label="Person / Character Name", visible=False)

			with gr.Accordion("Generation settings", open=False):
				temperature_slider = gr.Slider(
					minimum=0.0, maximum=2.0, value=0.6, step=0.05,
					label="Temperature",
					info="Higher values make the output more random, lower values make it more deterministic."
				)
				top_p_slider = gr.Slider(
					minimum=0.0, maximum=1.0, value=0.9, step=0.01,
					label="Top-p"
				)
				max_tokens_slider = gr.Slider(
					minimum=1, maximum=2048, value=512, step=1,
					label="Max New Tokens",
					info="Maximum number of tokens to generate.  The model will stop generating if it reaches this limit."
				)
			
			log_prompt = gr.Checkbox(value=True, label="Help improve JoyCaption by logging your text query")
		
		with gr.Column():
			prompt_box = gr.Textbox(lines=4, label="Prompt", interactive=True)

			# Show the name input box only when the specific option is selected
			extra_options.change(
				toggle_name_box,
				inputs=extra_options,
				outputs=name_input,
			)

			# Auto-update prompt box whenever any of the inputs change
			for ctrl in (caption_type, caption_length, extra_options, name_input):
				ctrl.change(
					build_prompt,
					inputs=[caption_type, caption_length, extra_options, name_input],
					outputs=prompt_box,
				)
			
			run_button = gr.Button("Caption")

			output_caption = gr.Textbox(label="Caption")
	
	run_button.click(
		chat_joycaption,
		inputs=[input_image, prompt_box, temperature_slider, top_p_slider, max_tokens_slider, log_prompt],
		outputs=output_caption,
	)

	# Initial prompt
	prompt_box.value = build_prompt(caption_type.value, caption_length.value, extra_options.value, name_input.value)

	gr.Markdown(DESCRIPTION)


if __name__ == "__main__":
    demo.launch()