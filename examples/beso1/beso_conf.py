# BESO config: examples/beso (Chen 2026-style stiffness TO, see backend/oc4_methodology_chen2026.py)
# Run from this directory: python beso_main.py

path = r"D:\python_project\beso_ai\examples\beso"
path_calculix = r"D:\freecad\bin\ccx.exe"

file_name = "Analysis-beso.inp"

elset_name = "design_space"
domain_optimized[elset_name] = True
domain_density[elset_name] = [7.833e-12, 7.833e-6]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 1000.0e6)], [("stress_von_Mises", 1000.0)]]
domain_material[elset_name] = ["*ELASTIC \n200000e-6,  0.27", "*ELASTIC \n200000,  0.27"]
domain_same_state[elset_name] = False

elset_name = "nondesign_space"
domain_optimized[elset_name] = False
domain_density[elset_name] = [7.833e-12, 7.833e-6]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 1000.0e6)], [("stress_von_Mises", 1000.0)]]
domain_material[elset_name] = ["*ELASTIC \n200000e-6,  0.27", "*ELASTIC \n200000,  0.27"]
domain_same_state[elset_name] = False

mass_goal_ratio = 0.15
continue_from = ""
filter_list = [["simple", "auto"]]

optimization_base = "stiffness"
cpu_cores = 0
FI_violated_tolerance = 1
decay_coefficient = -0.2
shells_as_composite = False
reference_points = "integration points"
reference_value = "max"
sensitivity_averaging = False
mass_addition_ratio = 0.04
mass_removal_ratio = 0.08
ratio_type = "relative"
compensate_state_filter = True
steps_superposition = []
iterations_limit = "auto"
tolerance = 1e-3
displacement_graph = []
save_iteration_results = 1
save_solver_files = ""
save_resulting_format = "inp vtk"
