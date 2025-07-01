from typing import List, Dict, Any, Optional
from bson.objectid import ObjectId

# Local imports for DBManager and Image classes
from aidb.dbmanager import DBManager
from aidb.image import Image # Assuming Image class is in image_class.py

class Query:
    """
    A class to perform queries on image metadata stored in MongoDB
    and return results as a list of Image objects.
    """

    def __init__(self, db_manager: DBManager) -> None:
        """
        Initializes the Query object with a reference to the DBManager.

        Args:
            db_manager (DBManager): An instance of the DBManager class.
        """
        if not isinstance(db_manager, DBManager):
            raise TypeError(f"db_manager must be an instance of DBManager. {db_manager}")
        
        self._db_manager = db_manager
        print("Query object initialized.")

    def query_images(self, query: Optional[Dict[str, Any]] = None) -> List[Image]:
        """
        Queries the 'images' collection in the database and returns a list
        of Image objects matching the given query.

        Args:
            query (Optional[Dict[str, Any]]): A dictionary representing the MongoDB query.
                                               If None, all image documents will be returned.
                                               When querying by '_id' or 'container_db_id',
                                               ensure the values are ObjectId instances.

        Returns:
            List[Image]: A list of Image objects matching the query. Returns an empty list
                         if no images are found or if there's a database error.
        """
        print(f"Executing query for images: {query}")
        
        # Ensure _id and container_db_id in query are ObjectId if they are strings
        processed_query = {}
        if query:
            for key, value in query.items():
                if key == "_id" or key == "container_db_id":
                    try:
                        processed_query[key] = ObjectId(value)
                    except Exception:
                        print(f"Warning: Invalid ObjectId format for '{key}': {value}. Skipping this query parameter.")
                        # If an invalid ObjectId is provided, it's safer to skip it
                        # or raise an error, depending on desired strictness.
                        continue
                else:
                    processed_query[key] = value

        image_docs = self._db_manager.find_documents('images', processed_query)
        
        image_objects: List[Image] = []
        if image_docs:
            for doc in image_docs:
                # MongoDB's _id is an ObjectId, convert to string for Image class constructor
                if '_id' in doc:
                    try:
                        image_objects.append(Image(self._db_manager, str(doc['_id'])))
                    except ValueError as e:
                        print(f"Error creating Image object for document {doc.get('_id')}: {e}")
                else:
                    print(f"Warning: Document found without '_id' field: {doc}")
        else:
            print("No image documents found matching the query.")
            
        return image_objects

# Example Usage (for testing purposes, typically in a separate script)
# if __name__ == "__main__":
#     # Assuming you have a running MongoDB and db_manager.py and image_class.py in the same directory
#     # Initialize DBManager
#     db_manager_instance = DBManager(host='localhost', port=27017, db_name='metadata_db')

#     if db_manager_instance.db: # Only proceed if DBManager connected successfully
#         query_handler = Query(db_manager_instance)

#         # --- Example 1: Add a dummy container and image for querying ---
#         print("\n--- Setting up dummy data for query test ---")
#         test_dir = pathlib.Path("query_test_container")
#         test_dir.mkdir(exist_ok=True)
#         (test_dir / "query_image_1.jpg").write_text("dummy image content 1")
#         (test_dir / "query_image_2.png").write_text("dummy image content 2")
        
#         container_id = db_manager_instance.add_container(str(test_dir))
#         
#         # Give some time for async operations if any, or ensure they complete
#         # In a real app, you might have more robust ways to ensure data is written
#         import time
#         time.sleep(1) 

#         # --- Example 2: Query all images ---
#         print("\n--- Querying all images ---")
#         all_images = query_handler.query_images()
#         print(f"Found {len(all_images)} images:")
#         for img in all_images:
#             print(f"  Image ID: {img.image_id}, Full Path: {img.get_full_path()}")
#             # You can now use methods from the Image class on these objects
#             # e.g., img.update_rating(4)

#         # --- Example 3: Query images by container_db_id ---
#         if container_id:
#             print(f"\n--- Querying images by container ID: {container_id} ---")
#             images_in_container = query_handler.query_images({"container_db_id": container_id})
#             print(f"Found {len(images_in_container)} images in container {container_id}:")
#             for img in images_in_container:
#                 print(f"  Image ID: {img.image_id}, Full Path: {img.get_full_path()}")

#         # --- Example 4: Query images by a custom field (e.g., rating) ---
#         # First, update a dummy image's rating to make it queryable
#         if all_images:
#             first_image_id = all_images[0].image_id
#             print(f"\n--- Updating rating of image {first_image_id} to 5 ---")
#             db_manager_instance.update_image(first_image_id, rating=5)
#             time.sleep(1) # Give time for update to propagate

#             print("\n--- Querying images with rating 5 ---")
#             high_rated_images = query_handler.query_images({"rating": 5})
#             print(f"Found {len(high_rated_images)} images with rating 5:")
#             for img in high_rated_images:
#                 print(f"  Image ID: {img.image_id}, Rating: {db_manager_instance.find_documents('images', {'_id': ObjectId(img.image_id)})[0].get('rating')}")


#         # --- Clean up dummy data ---
#         print("\n--- Cleaning up dummy data ---")
#         if container_id:
#             db_manager_instance.delete_document('containers', {"_id": ObjectId(container_id)})
#         db_manager_instance.delete_document('images', {"container_local_path": str(test_dir)})
#         if test_dir.exists():
#             for f in test_dir.iterdir():
#                 f.unlink()
#             test_dir.rmdir()
#         print("Dummy data cleaned up.")

#     db_manager_instance.close_connection()

