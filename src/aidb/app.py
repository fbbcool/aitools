import gradio as gr
from aidb.dbmanager import DBManager
from aidb.query import Query
from aidb.dbstatistics import Statistics
from aidb.image import Image
from aidb.tagger import TAGS_CUSTOM
from aidb.app.cell_image import AppImageCell
from aidb.app.tab_search_and_rate import AppTabSearchAndRate
from typing import Final, Optional, List, Dict, Any, Tuple
import html
import json # Import json for robust string escaping

# Define images per page constant
IMAGES_PER_PAGE: Final = 250
TAGS_TRIGGER: Final = ["1gts", "1hairy", "1legs", "1fbb", "1busty"]

class AIDBGradioApp:
    """
    A Gradio-based frontend for the AIDB image metadata management system.
    This class will encapsulate the Gradio UI components and their interactions
    with the DBManager.
    """

    def __init__(self, db_manager: DBManager) -> None:
        """
        Initializes the Gradio application with a reference to the DBManager.

        Args:
            db_manager (DBManager): An instance of the DBManager class.
        """
        if not isinstance(db_manager, DBManager):
            raise TypeError("db_manager must be an instance of DBManager.")
        
        self._db_manager = db_manager
        self._query_handler = Query(db_manager)
        self._statistics_handler = Statistics(db_manager)
        print("AIDBGradioApp initialized with DBManager, Query, and Statistics references.")

        # hidden update triggers
        self._get_full_image_data_trigger_elem_id = "get_full_image_data_trigger_btn"
        self._rating_update_trigger_elem_id = "rating_update_trigger_btn"
        self._scene_update_trigger_elem_id = "scene_update_trigger_btn"
        # hidden data busses
        self._image_id_bus_elem_id = "image_id_bus_elem"
        self._rating_data_bus_elem_id = "rating_data_bus_elem"
        self._scene_data_bus_elem_id = "scene_data_bus_elem"

        self.interface = self._create_interface()

    def _create_interface(self):
        """
        Creates the Gradio interface for the application.
        This method will define the UI components and their associated functions.
        """
        # Get all tags once to populate dropdowns
        all_wd_tags = self._get_sorted_wd_tags_for_dropdown()

        # Add an empty string option to allow "None" selection
        dropdown_choices = [""] + all_wd_tags # Empty string for "None"

        with gr.Blocks() as demo:
            gr.Markdown("# AIDB Image Metadata Manager")
            gr.Markdown("Welcome to the AIDB frontend. Use the search options below.")

            # State variables for pagination (only advanced search cache is needed)
            advanced_search_image_cache = gr.State(value=[])
            advanced_search_current_page = gr.State(value=1)

            # --- Hidden Components for Robust Event Handling ---
            # Trigger buttons (no data, just event triggers)
            get_full_image_data_trigger = gr.Button("Get Full Image Data Trigger", visible=False, elem_id=self._get_full_image_data_trigger_elem_id)
            rating_update_trigger = gr.Button("Hidden Rating Update Trigger", visible=False, elem_id=self._rating_update_trigger_elem_id)
            scene_update_trigger = gr.Button("Hidden Scene Update Trigger", visible=False, elem_id=self._scene_update_trigger_elem_id)

            # Data bus textboxes (hold data passed from JS to Python)
            image_id_bus = gr.Textbox(visible=False, elem_id=self._image_id_bus_elem_id)
            rating_data_bus = gr.Textbox(visible=False, elem_id=self._rating_data_bus_elem_id)
            scene_data_bus = gr.Textbox(visible=False, elem_id=self._scene_data_bus_elem_id)
            
            # Data bus textboxes for the image modal
            modal_img_data_bus = gr.Textbox(visible=False, elem_id="modal_img_data_bus_elem")
            modal_details_data_bus = gr.Textbox(visible=False, elem_id="modal_details_data_bus_elem")
            # --- End Hidden Components ---

            AppImageCell.html_image_modal()

            with gr.Tab("Database Status"):
                status_output = gr.Textbox(label="MongoDB Connection Status", interactive=False)
                check_status_btn = gr.Button("Check DB Connection")
                check_status_btn.click(self._check_db_status, outputs=status_output)

            AppTabSearchAndRate._create_interface()            
            with gr.Tab("Image Search"): # Renamed tab for clarity
                gr.Markdown("## Advanced Image Search with Mandatory and Optional Tags")
                gr.Markdown("Select up to 3 mandatory tags (all must be present) and up to 3 optional tags (contribute to score).")

                with gr.Row():
                    mandatory_tag_1 = gr.Dropdown(label="Mandatory Tag 1", choices=dropdown_choices, value="", allow_custom_value=False, interactive=True)
                    mandatory_tag_2 = gr.Dropdown(label="Mandatory Tag 2", choices=dropdown_choices, value="", allow_custom_value=False, interactive=True)
                    mandatory_tag_3 = gr.Dropdown(label="Mandatory Tag 3", choices=dropdown_choices, value="", allow_custom_value=False, interactive=True)
                
                with gr.Row():
                    optional_tag_1 = gr.Dropdown(label="Optional Tag 1", choices=dropdown_choices, value="", allow_custom_value=False, interactive=True)
                    optional_tag_2 = gr.Dropdown(label="Optional Tag 2", choices=dropdown_choices, value="", allow_custom_value=False, interactive=True)
                    optional_tag_3 = gr.Dropdown(label="Optional Tag 3", choices=dropdown_choices, value="", allow_custom_value=False, interactive=True)
                
                with gr.Row():
                    rating_min = gr.Dropdown(label="Rating Min", choices=[str(x) for x in list(range(-2, 6))], value="3", allow_custom_value=False, interactive=True)
                    rating_max = gr.Dropdown(label="Rating Max", choices=[str(x) for x in list(range(-2, 6))], value="5", allow_custom_value=False, interactive=True)
                with gr.Row():
                    operation = gr.Dropdown(label="Operation", choices=["None", "Rate", "Scene"], value="Rate", allow_custom_value=False, interactive=True)
                    bodypart = gr.Dropdown(label="Bodypart", choices=["Ignore", "Empty"] + TAGS_CUSTOM["bodypart"], value="Ignore", allow_custom_value=False, interactive=True)
                
                search_button = gr.Button("Search Images")
                
                with gr.Column(visible=True) as advanced_search_list_view:
                    # in the title, the number of selected images should be shown
                    curr_label = "Matching Images (Highest Score First)"
                    advanced_search_html_display = gr.HTML(label=curr_label)
                    with gr.Row():
                        advanced_search_prev_btn = gr.Button("Previous Page")
                        advanced_search_page_info = gr.Textbox(label="Page", interactive=False, scale=0)
                        advanced_search_next_btn = gr.Button("Next Page")
                        advanced_search_go_to_page_num = gr.Number(label="Go to Page", value=1, precision=0, scale=0)
                        advanced_search_go_to_page_btn = gr.Button("Go")
                        refresh_button = gr.Button("Refresh Current Page") # NEW Refresh button

                search_button.click(
                    self._imgs_search_and_op,
                    inputs=[
                        mandatory_tag_1, mandatory_tag_2, mandatory_tag_3,
                        optional_tag_1, optional_tag_2, optional_tag_3, rating_min, rating_max,operation,bodypart
                    ],
                    outputs=[advanced_search_html_display, advanced_search_image_cache, advanced_search_current_page, advanced_search_page_info]
                )

                advanced_search_prev_btn.click(
                    self._paginate_images,
                    inputs=[advanced_search_image_cache, advanced_search_current_page, gr.State(-1)],
                    outputs=[advanced_search_html_display, advanced_search_current_page, advanced_search_page_info]
                )
                advanced_search_next_btn.click(
                    self._paginate_images,
                    inputs=[advanced_search_image_cache, advanced_search_current_page, gr.State(1)],
                    outputs=[advanced_search_html_display, advanced_search_current_page, advanced_search_page_info]
                )
                advanced_search_go_to_page_btn.click(
                    self._go_to_specific_page,
                    inputs=[advanced_search_image_cache, advanced_search_current_page, advanced_search_go_to_page_num],
                    outputs=[advanced_search_html_display, advanced_search_current_page, advanced_search_page_info]
                )

                # NEW: Refresh button click event
                refresh_button.click(
                    self._refresh_image_grid,
                    inputs=[advanced_search_image_cache, advanced_search_current_page],
                    outputs=[advanced_search_html_display, advanced_search_current_page, advanced_search_page_info]
                )
            
            # Link hidden triggers to functions
            get_full_image_data_trigger.click(
                self._get_full_image_data_for_modal,
                inputs=[image_id_bus],
                outputs=[modal_img_data_bus, modal_details_data_bus]
            ).then( # Chaining .then() to update the modal after data is received
                None, # No Python function needed here, just JS
                [modal_img_data_bus, modal_details_data_bus], # Inputs are the data buses
                None, # No outputs to Gradio components for this JS part
                js="""
                (img_base64, details_json_string) => {
                    console.log('JS: Received data for modal. Updating modal content.');
                    const details = JSON.parse(details_json_string); // Parse the JSON string from the data bus

                    if (details.error) {
                        document.getElementById('fullPageImage').src = ''; // Clear image
                        document.getElementById('fullPageImageDetails').innerHTML = `
                            <h4>Error:</h4>
                            <p>${details.error}</p>
                        `;
                    } else {
                        document.getElementById('fullPageImage').src = 'data:image/png;base64,' + img_base64;
                        document.getElementById('fullPageImageDetails').innerHTML = `
                            <h4>Image Details:</h4>
                            <p><strong>ID:</strong> ${details.id}</p>
                            <p><strong>Full Path:</strong> ${details.full_path}</p>
                            <p><strong>Rating:</strong> ${details.rating}</p>
                            <p><strong>Category:</strong> ${details.category}</p>
                            <p><strong>Dimensions:</strong> ${details.dimensions_width}x${details.dimensions_height} ${details.dimensions_unit}</p>
                            <p><strong>Creation Date:</strong> ${details.creation_date}</p>
                            <p><strong>Last Modified Date:</strong> ${details.last_modified_date}</p>
                            <h4>WD Tags (Tag: Probability):</h4>
                            <pre>${details.tags_html}</pre>
                        `;
                    }
                    document.getElementById('fullPageImageOverlay').style.display = 'flex'; // Use flex to center
                }
                """
            )

            rating_update_trigger.click(
                self._update_image_rating, # Call the update function first
                inputs=[rating_data_bus], # Input is the data bus textbox
                outputs=[] # This function doesn't update UI directly
            ).then( # Chain .then() to refresh the grid
                self._refresh_image_grid,
                inputs=[advanced_search_image_cache, advanced_search_current_page],
                outputs=[advanced_search_html_display, advanced_search_current_page, advanced_search_page_info] # Update the grid
            )
            
            scene_update_trigger.click(
                self._update_image_scene, # Call the update function first
                inputs=[scene_data_bus], # Input is the data bus textbox
                outputs=[] # This function doesn't update UI directly
            ).then( # Chain .then() to refresh the grid
                self._refresh_image_grid,
                inputs=[advanced_search_image_cache, advanced_search_current_page],
                outputs=[advanced_search_html_display, advanced_search_current_page, advanced_search_page_info] # Update the grid
            )
            
        return demo

    def _check_db_status(self) -> str:
        """
        Checks the status of the MongoDB connection.
        """
        if self._db_manager.client and self._db_manager.db:
            try:
                self._db_manager.client.admin.command('ping')
                return "Successfully connected to MongoDB!"
            except Exception as e:
                return f"MongoDB connection failed: {e}"
        else:
            return "MongoDB client or database not initialized."

    def _get_sorted_wd_tags_for_dropdown(self) -> List[str]:
        """
        Retrieves all unique WD tags, sorted by their absolute occurrence
        in descending order, for populating the Gradio dropdown.
        """
        print("Fetching sorted WD tags for dropdown...")
        tag_counts = self._statistics_handler.get_absolute_tag_occurrence()
        
        # Sort tags by count in descending order
        sorted_tags = sorted(tag_counts.items(), key=lambda item: item[1], reverse=True)
        
        # Return only the tag names
        tag_names = [tag for tag, count in sorted_tags]
        print(f"Found {len(tag_names)} unique WD tags.")
        return tag_names

    def _generate_image_html(self, images_on_page_data: list[Image]) -> str:
        """
        Generates HTML for a two-column grid of images with captions, rating controls,
        and contributing tags.
        Includes client-side JavaScript for image click to show full-size overlay.
        """
        # Get the dynamically generated IDs for the hidden Gradio components
        get_full_image_data_trigger_id = self._get_full_image_data_trigger_elem_id
        rating_update_trigger_id = self._rating_update_trigger_elem_id
        scene_update_trigger_id = self._scene_update_trigger_elem_id
        
        html_content = f"""
        <style>
            .image-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 15px;
                padding: 10px;
            }}
            .image-item {{
                border: 1px solid #ddd;
                border-radius: 8px;
                overflow: hidden;
                text-align: center;
                background-color: #333333; /* Dark grey background */
                padding-bottom: 10px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                height: 100%;
            }}
            .image-item img {{
                max-width: 100%;
                height: auto;
                display: block;
                margin: 0 auto;
                border-bottom: 1px solid #eee;
                padding: 5px;
                cursor: pointer; /* Indicate clickable only on image itself */
            }}
            .image-item-warning {{
                border: 1px solid #ddd;
                border-radius: 8px;
                overflow: hidden;
                text-align: center;
                background-color: #aaaa33; /* Dark grey background */
                padding-bottom: 10px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                height: 100%;
            }}
            .image-item-error img {{
                max-width: 100%;
                height: auto;
                display: block;
                margin: 0 auto;
                border-bottom: 1px solid #eee;
                padding: 5px;
                cursor: pointer; /* Indicate clickable only on image itself */
            }}
            .image-item-error {{
                border: 1px solid #ddd;
                border-radius: 8px;
                overflow: hidden;
                text-align: center;
                background-color: #ff3333; /* Dark grey background */
                padding-bottom: 10px;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                height: 100%;
            }}
            .image-item-warning img {{
                max-width: 100%;
                height: auto;
                display: block;
                margin: 0 auto;
                border-bottom: 1px solid #eee;
                padding: 5px;
                cursor: pointer; /* Indicate clickable only on image itself */
            }}
            .image-caption {{
                font-size: 0.9em;
                color: #ffffff; /* White font for caption */
                margin-top: 5px;
                padding: 0 10px;
                word-wrap: break-word;
            }}
            .image-controls {{
                margin-top: 10px;
                padding: 0 10px;
                color: #ffffff; /* White font for controls */
            }}
            .operation-radio-group {{
                display: flex;
                justify-content: center;
                gap: 5px;
                flex-wrap: wrap; /* Allow wrapping for smaller screens */
            }}
            .operation-radio-group input[type="radio"] {{
                display: none; /* Hide default radio button */
            }}
            .operation-radio-group label {{
                padding: 5px 8px;
                border: 1px solid #ccc;
                border-radius: 5px;
                cursor: pointer;
                font-size: 0.8em;
                transition: all 0.2s ease;
                background-color: #555555; /* Slightly lighter grey for radio buttons */
                color: #ffffff; /* White font for radio button labels */
            }}
            .operation-radio-group input[type="radio"]:checked + label {{
                background-color: #4CAF50; /* Green for selected */
                color: white;
                border-color: #4CAF50;
                box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            }}
            .operation-radio-group label:hover {{
                background-color: #777777; /* Darker hover for radio buttons */
            }}
            .operation-checkbox-group {{
                display: flex;
                justify-content: center;
                gap: 5px;
                flex-wrap: wrap; /* Allow wrapping for smaller screens */
            }}
            .operation-checkbox-group input[type="checkbox"] {{
                display: none; /* Hide default checkbox button */
            }}
            .operation-checkbox-group label {{
                padding: 5px 8px;
                border: 1px solid #ccc;
                border-radius: 5px;
                cursor: pointer;
                font-size: 0.8em;
                transition: all 0.2s ease;
                background-color: #555555; /* Slightly lighter grey for checkbox buttons */
                color: #ffffff; /* White font for checkbox button labels */
            }}
            .operation-checkbox-group input[type="checkbox"]:checked + label {{
                background-color: #4CAF50; /* Green for selected */
                color: white;
                border-color: #4CAF50;
                box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            }}
            .operation-checkbox-group label:hover {{
                background-color: #777777; /* Darker hover for checkbox buttons */
            }}
            .tag-contribution {{
                font-size: 0.8em;
                color: #cccccc; /* Light grey for tag contribution text */
                margin-top: 5px;
                padding: 0 10px;
                text-align: left;
            }}
            .tag-contribution strong {{
                color: #ffffff; /* White font for strong tags */
            }}
        </style>
        <div class="image-grid">
        """

        for img in images_on_page_data:
            # Call AppImageCell.make to get the HTML for each cell
            html_content += AppImageCell.make(
                img,
                get_full_image_data_trigger_id=get_full_image_data_trigger_id,
                rating_update_trigger_id=rating_update_trigger_id,
                scene_update_trigger_id=scene_update_trigger_id,
            )
        
        html_content += "</div>"
        return html_content

    def _paginate_images(self, 
                         image_cache: List[Image],
                         current_page: int, 
                         direction: int
                         ) -> Tuple[str, int, str]:
        """
        Handles pagination for image displays.
        `direction` is -1 for previous, 1 for next.
        """
        if not image_cache:
            return "", 1, "Page 0/0"

        total_images = len(image_cache)
        total_pages = (total_images + IMAGES_PER_PAGE - 1) // IMAGES_PER_PAGE
        
        new_page = current_page + direction
        new_page = max(1, min(new_page, total_pages)) # Clamp page number

        start_idx = (new_page - 1) * IMAGES_PER_PAGE
        end_idx = start_idx + IMAGES_PER_PAGE

        images_on_page = image_cache[start_idx:end_idx]
        html_output = self._generate_image_html(images_on_page)
        page_info_text = f"Page {new_page}/{total_pages}"
        
        return html_output, new_page, page_info_text

    def _go_to_specific_page(self,
                             image_cache: List[Image],
                             current_page: int, # This is the current page before the jump
                             target_page_number: float # Gradio's Number component returns float
                            ) -> Tuple[str, int, str]:
        """
        Jumps to a specific page in the image display.
        """
        if not image_cache:
            return "", 1, "Page 0/0"

        total_images = len(image_cache)
        total_pages = (total_images + IMAGES_PER_PAGE - 1) // IMAGES_PER_PAGE

        # Ensure target_page_number is an integer and within valid bounds
        target_page = int(target_page_number)
        target_page = max(1, min(target_page, total_pages))

        # Call paginate_images with the calculated target page and no relative direction
        return self._paginate_images(image_cache, target_page, 0)


    def _imgs_search_and_op(self, 
                                     mand_tag1: Optional[str], mand_tag2: Optional[str], mand_tag3: Optional[str],
                                     opt_tag1: Optional[str], opt_tag2: Optional[str], opt_tag3: Optional[str],
                                     rating_min: Optional[str], rating_max: Optional[str],
                                     operation: Optional[str],
                                     bodypart: Optional[str],
                                     ) -> Tuple[str, List[Image], int, str]:
        """
        Performs an advanced search and initializes pagination.
        Returns (html_content, image_cache, current_page, page_info_text).
        """
        mandatory_tags = [tag for tag in [mand_tag1, mand_tag2, mand_tag3] if tag]
        optional_tags = [tag for tag in [opt_tag1, opt_tag2, opt_tag3] if tag]

        # get scored image list
        imgs = self._query_handler.query_by_tags(mandatory_tags, optional_tags, int(rating_min), int(rating_max),bodypart)

        # add chosen operation to images
        for img in imgs:
            img.operation = operation.lower() if operation else 'nop'

        print(f"Found {len(imgs)} images matching advanced search criteria.")

        # Initialize pagination to the first page
        total_images = len(imgs)
        total_pages = (total_images + IMAGES_PER_PAGE - 1) // IMAGES_PER_PAGE
        current_page = 1

        start_idx = (current_page - 1) * IMAGES_PER_PAGE
        end_idx = start_idx + IMAGES_PER_PAGE
        
        images_on_page = imgs[start_idx:end_idx]
        html_output = self._generate_image_html(images_on_page)
        page_info_text = f"Page {current_page}/{total_pages} ({total_images} imgs)"

        return html_output, imgs, current_page, page_info_text

    def _get_full_image_data_for_modal(self, image_id: str) -> Tuple[str, str]:
        """
        Fetches full image data for the modal display.
        Returns a raw base64 string and a JSON-serialized string of the image details.
        These strings are intended to be placed in hidden Textbox components (data buses).
        """
        print(f"DEBUG: _get_full_image_data_for_modal called for image ID: {image_id}")

        if not image_id:
            print("ERROR: Received empty or invalid image ID for modal data.")
            return "", json.dumps({"error": "Invalid image ID provided."})

        try:
            img_obj = Image(self._db_manager, image_id)
        except ValueError as e:
            print(f"ERROR: Invalid ObjectId for image ID '{image_id}': {e}")
            return "", json.dumps({"error": f"Invalid image ID format: {image_id}"})
            
        image_data = img_obj.data
        if image_data is None:
            print(f"ERROR: Image with ID '{image_id}' not found in the database or data could not be retrieved.")
            return "", json.dumps({"error": f"Image with ID '{image_id}' not found in the database."})

        pil_img = img_obj.pil
        if pil_img is None:
            print(f"ERROR: Could not load PIL image file for image ID: {image_id}.")
            return "", json.dumps({"error": f"Could not load image file for ID: {image_id}."})

        full_img_base64 = AppImageCell._pil_to_base64(pil_img)

        tags_wd = image_data.get('tags', {}).get('tags_wd', {})
        sorted_tags_wd = sorted(tags_wd.items(), key=lambda item: item[1], reverse=True)
        # Escape tag names to prevent potential HTML injection issues
        modal_formatted_tags = "".join([f"{html.escape(tag)}: {prob:.2f}<br>" for tag, prob in sorted_tags_wd])
        
        image_details = {
            "id": str(img_obj.id),
            "full_path": str(img_obj.get_full_path()) if img_obj.get_full_path() else "N/A",
            "rating": img_obj.data.get('rating', 'N/A'),
            "category": img_obj.data.get('category', 'N/A'),
            "dimensions_width": image_data.get('dimensions', {}).get('width', 'N/A'),
            "dimensions_height": image_data.get('dimensions', {}).get('height', 'N/A'),
            "dimensions_unit": image_data.get('dimensions', {}).get('unit', ''),
            "creation_date": image_data.get('creation_date', 'N/A'),
            "last_modified_date": image_data.get('last_modified_date', 'N/A'),
            "tags_html": modal_formatted_tags if modal_formatted_tags else 'No WD tags available.'
        }
        
        return full_img_base64, json.dumps(image_details)

    def _update_image_rating(self, 
                             rating_data_str: str,
                            ) -> None: # No outputs from this function
        """
        Updates an image's rating in the database.
        This function is triggered by a hidden button and receives its data from a hidden 'data bus' textbox.
        The UI refresh is handled by a subsequent .then() call in the event chain.
        """
        print(f"DEBUG: _update_image_rating called with data from bus: '{rating_data_str}'")

        if not rating_data_str or not isinstance(rating_data_str, str):
            print(f"ERROR: Invalid or empty data received for rating update: {rating_data_str}")
            gr.Warning("Could not update rating: Invalid data received from frontend.")
            return None

        # We expect a string like "image_id_val,new_rating_val"
        parts = rating_data_str.split(',')
        if len(parts) != 2:
            print(f"ERROR: Invalid data format for _update_image_rating: {rating_data_str}")
            gr.Warning(f"Could not update rating: Malformed data '{rating_data_str}'.")
            return None
        
        image_id = parts[0].strip()
        try:
            new_rating = int(parts[1].strip())
        except ValueError:
            print(f"ERROR: Invalid rating value received in data: {rating_data_str}")
            gr.Warning(f"Could not update rating: Invalid rating value in '{rating_data_str}'.")
            return None
        print(f"DEBUG: _update_image_rating called for image {image_id} with rating {new_rating}")
        # Update the database
        ret = self._db_manager.update_image(image_id, rating=new_rating)
        # This function now explicitly returns None, as it's not directly updating Gradio outputs.
        # give gradio info based on ret
        if ret and ret > 0:
            gr.Info(f"Rating for image {image_id} updated to {new_rating}.")
        else:
            gr.Warning(f"Failed to update rating for image {image_id}.")
            
        return None 

    def _update_image_scene(self, 
                             data_str: str,
                            ) -> None: # No outputs from this function
        """
        Updates an image's scene tag in the database.
        This function is triggered by a hidden button and receives its data from a hidden 'data bus' textbox.
        The UI refresh is handled by a subsequent .then() call in the event chain.
        """
        print(f"DEBUG: _update_scene_rating called with data from bus: '{data_str}'")

        if not data_str or not isinstance(data_str, str):
            print(f"ERROR: Invalid or empty data received for scene update: {data_str}")
            gr.Warning("Could not update scene: Invalid data received from frontend.")
            return None

        # We expect a string like "image_id,new_val"
        parts = data_str.split(',')
        if len(parts) != 2:
            print(f"ERROR: Invalid data format for _update_image_scene: {data_str}")
            gr.Warning(f"Could not update scene: Malformed data '{data_str}'.")
            return None
        
        image_id = parts[0].strip()
        try:
            new_data = parts[1].strip()
        except ValueError:
            print(f"ERROR: Invalid scene value received in data: {data_str}")
            gr.Warning(f"Could not update: Invalid scene value in '{data_str}'.")
            return None
        print(f"DEBUG: _update_image_scene called for image {image_id} with scene {new_data}")
        # Update the database
        img = Image(self._db_manager, image_id)
        bodyparts = img.get_tags_custom("bodypart")
        if new_data not in bodyparts:
            bodyparts.append(new_data)
        else:
            # remove new_data from bodyparts
            bodyparts.remove(new_data)
            
        ret = img.set_tags_custom("bodypart", bodyparts)
        # This function now explicitly returns None, as it's not directly updating Gradio outputs.
        # give gradio info based on ret
        if ret and ret > 0:
            gr.Info(f"Scene tag for image {image_id} updated to {new_data}.")
        else:
            gr.Warning(f"Failed to update scene tag for image {image_id}.")
            
        return None 


    def _refresh_image_grid(self, 
                            advanced_search_image_cache: List[Image],
                            advanced_search_current_page: int
                           ) -> Tuple[str, int, str]:
        """
        Refreshes the image grid display based on the current cache and page.
        """
        print(f"DEBUG: _refresh_image_grid called for page {advanced_search_current_page}")
        advanced_search_html, advanced_search_page, advanced_search_page_info_text = self._paginate_images(
            advanced_search_image_cache, advanced_search_current_page, 0
        )
        return (advanced_search_html, advanced_search_page, advanced_search_page_info_text)


    def launch(self, **kwargs):
        print("Launching Gradio application...")
        self.interface.launch(**kwargs)

# Example Usage (for testing purposes, typically in a separate script or main application file)
if __name__ == "__main__":
    # Initialize DBManager (assuming MongoDB is running)
    db_manager_instance = DBManager(config_file='/Volumes/data/Project/AI/REPOS/aitools/src/aidb/dbmanager.yaml')

    # Create and launch the Gradio app
    if db_manager_instance.db is not None: # Only proceed if DBManager connected successfully
        app = AIDBGradioApp(db_manager_instance)
        app.launch()
    else:
        print("Could not initialize DBManager. Gradio app will not launch.")
