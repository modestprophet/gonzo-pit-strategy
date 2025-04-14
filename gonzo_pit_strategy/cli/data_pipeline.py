#Process data and save transformers
# TODO: Explore saving OHE and scalar to DB, config, or something other than pickle
import os
from training.data_pipeline import DataPipeline


current_file_path = os.path.abspath(__file__)  # Absolute path to this script
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file_path)) ) # Go up three levels

print(current_file_path)
print(project_root)

# pipeline_project_root = get_project_root()
config_path = os.path.join(project_root, 'config', 'pipeline_race_history.json')

pipeline = DataPipeline(config_path=config_path)
df = pipeline.process()

# # Later, load transformers for inference
# pipeline = DataPipeline()
# pipeline.load_artifacts("20230415123456_abc123def456")
#
# # Load the data
# df = pipeline.load_checkpoint("f1_race_data_2021", "20230415123456_abc123def456")
#
# # Apply transformations for inference (useful in your model predictor)
# for step in pipeline.steps:
#     if step.name in ["CategoricalEncoder", "NumericalScaler"]:
#         new_data = step.process(new_data)