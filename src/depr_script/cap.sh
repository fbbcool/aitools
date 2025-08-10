#!/bin/sh
curr_dir=`pwd`
train_dir='/Volumes/data/Project/AI/venv/kohya_ss'
source_dir=$1

cd $train_dir
source venv/bin/activate
accelerate launch "./finetune/tag_images_by_wd14_tagger.py"\
	--onnx\
	--batch_size=1\
	--general_threshold=0.35\
	--character_threshold=0.35\
	--caption_extension=".caption_wd14"\
	--caption_separator=","\
  	--model="SmilingWolf/wd-v1-4-convnextv2-tagger-v2"\
	--max_data_loader_n_workers="2"\
  	--frequency_tags $source_dir
