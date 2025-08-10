source /kohya_ss/venv/bin/activate
accelerate launch\
	"./finetune/tag_images_by_wd14_tagger.py"\
	--batch_size=8 --general_threshold=0.65\
	--character_threshold=0.65\
	--caption_extension=".caption_wd14"\
	--model="SmilingWolf/wd-v1-4-convnextv2-tagger-v2"\
	--max_data_loader_n_workers="2" --recursive --debug\
	--remove_underscore --frequency_tags\
	"/root/train/build/pools"