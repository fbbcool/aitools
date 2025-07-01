from aidb.dbmanager import DBManager
from aidb.image import Image # Import the Image class
from typing import Dict, Any, List, Optional
from collections import defaultdict

class Statistics:
    """
    A class to generate various statistics from the image and container metadata
    stored in the MongoDB database.
    """

    def __init__(self, db_manager: DBManager) -> None:
        """
        Initializes the Statistics object with a reference to the DBManager.

        Args:
            db_manager (DBManager): An instance of the DBManager class.
        """
        if not isinstance(db_manager, DBManager):
            raise TypeError("db_manager must be an instance of DBManager.")
        
        self._db_manager = db_manager
        print("Statistics object initialized.")

    def get_average_tag_occurrence(self, images: Optional[List[Image]] = None) -> Dict[str, float]:
        """
        Calculates the average occurrence (probability) of each unique tag
        found in the 'tags_wd' field.

        Args:
            images (Optional[List[Image]]): A list of Image objects to process.
                                            If None or empty, all images from the
                                            database will be used.

        Returns:
            Dict[str, float]: A dictionary where keys are tag names and values
                              are their average occurrence probabilities.
                              Returns an empty dictionary if no images are found
                              or no tags are present.
        """
        print("Calculating average tag occurrence...")
        
        tag_probabilities_sum: Dict[str, float] = defaultdict(float)
        tag_occurrence_count: Dict[str, int] = defaultdict(int)

        # Determine which images to process
        if images:
            images_to_process = images
            print(f"Processing {len(images_to_process)} provided images for average tag occurrence.")
        else:
            # Retrieve all image documents if no specific list is provided
            print("No specific images provided, fetching all images from database.")
            image_docs = self._db_manager.find_documents('images')
            if not image_docs:
                print("No image documents found in the database.")
                return {}
            # Convert documents to Image objects for consistent processing
            images_to_process = [Image(self._db_manager, str(doc['_id'])) for doc in image_docs if '_id' in doc]
            print(f"Found {len(images_to_process)} images in the database.")


        if not images_to_process:
            print("No images to process for average tag occurrence.")
            return {}

        for img_obj in images_to_process:
            # Access tags through the Image object's data property
            image_data = img_obj.data
            if image_data and 'tags' in image_data and 'tags_wd' in image_data['tags']:
                wd_tags = image_data['tags']['tags_wd']
                for tag, probability in wd_tags.items():
                    tag_probabilities_sum[tag] += probability
                    tag_occurrence_count[tag] += 1
            else:
                # print(f"Image {img_obj.image_id} has no 'tags' or 'tags_wd' field.")
                pass # Silently skip images without tag data

        average_tag_occurrence: Dict[str, float] = {}
        for tag, total_probability in tag_probabilities_sum.items():
            count = tag_occurrence_count[tag]
            if count > 0:
                average_tag_occurrence[tag] = total_probability / count
            else:
                average_tag_occurrence[tag] = 0.0 
        
        print(f"Finished calculating average tag occurrence for {len(average_tag_occurrence)} unique tags.")
        return average_tag_occurrence

    def get_absolute_tag_occurrence(self, images: Optional[List[Image]] = None) -> Dict[str, int]:
        """
        Calculates the absolute occurrence (frequency) of each unique tag
        found in the 'tags_wd' field.

        Args:
            images (Optional[List[Image]]): A list of Image objects to process.
                                            If None or empty, all images from the
                                            database will be used.

        Returns:
            Dict[str, int]: A dictionary where keys are tag names and values
                            are their absolute occurrence counts.
                            Returns an empty dictionary if no images are found
                            or no tags are present.
        """
        print("Calculating absolute tag occurrence...")
        
        tag_counts: Dict[str, int] = defaultdict(int)

        # Determine which images to process
        if images:
            images_to_process = images
            print(f"Processing {len(images_to_process)} provided images for absolute tag occurrence.")
        else:
            # Retrieve all image documents if no specific list is provided
            print("No specific images provided, fetching all images from database.")
            image_docs = self._db_manager.find_documents('images')
            if not image_docs:
                print("No image documents found in the database.")
                return {}
            # Convert documents to Image objects for consistent processing
            images_to_process = [Image(self._db_manager, str(doc['_id'])) for doc in image_docs if '_id' in doc]
            print(f"Found {len(images_to_process)} images in the database.")

        if not images_to_process:
            print("No images to process for absolute tag occurrence.")
            return {}

        for img_obj in images_to_process:
            # Access tags through the Image object's data property
            image_data = img_obj.data
            if image_data and 'tags' in image_data and 'tags_wd' in image_data['tags']:
                wd_tags = image_data['tags']['tags_wd']
                for tag in wd_tags.keys(): # Just count the presence of the tag
                    tag_counts[tag] += 1
            else:
                pass # Silently skip images without tag data

        print(f"Finished calculating absolute tag occurrence for {len(tag_counts)} unique tags.")
        return dict(tag_counts) # Convert defaultdict to a regular dict for return

    # Placeholder for future methods
    # def get_tag_frequency(self) -> Dict[str, int]:
    #     """
    #     Calculates the frequency of each tag across all images.
    #     """
    #     pass

    # def get_images_by_rating(self) -> Dict[str, int]:
    #     """
    #     Counts images by their rating.
    #     """
    #     pass

    # def get_container_statistics(self) -> List[Dict[str, Any]]:
    #     """
    #     Provides statistics per container, e.g., number of images, average rating.
    #     """
    #     pass

