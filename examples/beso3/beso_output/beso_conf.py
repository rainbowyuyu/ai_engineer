# Auto-generated: beso3 120° sectors + nondesign_space

path = r"D:\python_project\beso_ai\examples\beso3\beso_output"
path_calculix = r"D:\freecad\bin\ccx.exe"
file_name = "Analysis-beso_sectors.inp"

iterations_limit = 8

elset_name = "design_s0"
domain_optimized[elset_name] = True
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]
domain_material[elset_name] = ["*ELASTIC \n210000e-6,  0.3", "*ELASTIC \n210000,  0.3"]
domain_same_state[elset_name] = False

elset_name = "design_s1"
domain_optimized[elset_name] = False
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]
domain_material[elset_name] = ["*ELASTIC \n210000e-6,  0.3", "*ELASTIC \n210000,  0.3"]
domain_same_state[elset_name] = False

elset_name = "design_s2"
domain_optimized[elset_name] = False
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]
domain_material[elset_name] = ["*ELASTIC \n210000e-6,  0.3", "*ELASTIC \n210000,  0.3"]
domain_same_state[elset_name] = False

elset_name = "nondesign_space"
domain_optimized[elset_name] = False
domain_density[elset_name] = [1e-6, 1]
domain_thickness[elset_name] = [1.0, 1.0]
domain_offset[elset_name] = 0.0
domain_orientation[elset_name] = []
domain_FI[elset_name] = [[("stress_von_Mises", 450.0e6)], [("stress_von_Mises", 450.0)]]
domain_material[elset_name] = ["*ELASTIC \n210000e-6,  0.3", "*ELASTIC \n210000,  0.3"]
domain_same_state[elset_name] = False

mass_goal_ratio = 0.15
filter_list = [["simple", 1149.1592536047383]]
optimization_base = "stiffness"
save_iteration_results = 1
save_resulting_format = "inp vtk"
