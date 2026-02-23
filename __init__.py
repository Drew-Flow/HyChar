import bpy
import os
if "bake_logic" in locals():
    import importlib
    importlib.reload(bake_logic)
else:
    from . import bake_logic

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_PATH = os.path.join(ADDON_DIR, "resources", "CharLibrary.blend")

# --- GET GN OBJ ---
def get_obj1():
    return next((o for o in bpy.data.objects if o.name.startswith("Beard_GN")), None)
def get_obj2():
    return next((o for o in bpy.data.objects if o.name.startswith("Cape_GN")), None)
def get_obj3():
    return next((o for o in bpy.data.objects if o.name.startswith("Earrings_GN")), None)
def get_obj4():
    return next((o for o in bpy.data.objects if o.name.startswith("FaceAcc_GN")), None)
def get_obj5():
    return next((o for o in bpy.data.objects if o.name.startswith("Gloves_GN")), None)
def get_obj6():
    return next((o for o in bpy.data.objects if o.name.startswith("Hair_GN")), None)
def get_obj7():
    return next((o for o in bpy.data.objects if o.name.startswith("HeadAcc_GN")), None)
def get_obj8():
    return next((o for o in bpy.data.objects if o.name.startswith("Overpants_GN")), None)
def get_obj9():
    return next((o for o in bpy.data.objects if o.name.startswith("Overshirt_GN")), None)
def get_obj10():
    return next((o for o in bpy.data.objects if o.name.startswith("Pants_GN")), None)
def get_obj11():
    return next((o for o in bpy.data.objects if o.name.startswith("Shoes_GN")), None)
def get_obj12():
    return next((o for o in bpy.data.objects if o.name.startswith("Undershirt_GN")), None)

# --- 1. SPAWN OPERATOR ---
class HYCHAR_OT_spawn_character(bpy.types.Operator):
    bl_idname = "hychar.spawn_character"
    bl_label = "Spawn Character"
    bl_description = "Appends character from the internal addon library folder"

    def execute(self, context):
        # 1. Force absolute path
        filepath = LIB_PATH
        
        # 2. Debug print
        print(f"HyChar Debug: Looking for library at {filepath}")

        if not os.path.exists(filepath):
            # 3. Error Message
            self.report({'ERROR'}, f"File not found: {os.path.basename(filepath)}. Check console for full path.")
            return {'CANCELLED'}

        coll_name = "Master_Character_Collection"

        with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
            if coll_name in data_from.collections:
                data_to.collections = [coll_name]
        
        for coll in data_to.collections:
            if coll:
                context.scene.collection.children.link(coll)
                
        self.report({'INFO'}, "Character Spawned!")
        
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                # Loop through all spaces in the 3D area (usually just one, but safer)
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        # Stay in RENDERED if they are already there
                        if space.shading.type in {'SOLID', 'WIREFRAME'}:
                            space.shading.type = 'MATERIAL'
        return {'FINISHED'}

# --- 2. BAKE OPERATOR ---
class MESH_OT_clone_factory_final(bpy.types.Operator):
    bl_idname = "mesh.clone_factory_final"
    bl_label = "Bake & Clone Hierarchy"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        PREFIX = context.scene.custom_rig_prefix
        RIG_NAME = "CharRig" 
        master_rig = bpy.data.objects.get(RIG_NAME)
        
        if not master_rig:
            self.report({'ERROR'}, f"Rig '{RIG_NAME}' not found!")
            return {'CANCELLED'}
        
        # --- SWITCH TO REST POSE ---
        # ensures GeoNodes meshes are captured in their neutral state
        old_pose_type = master_rig.data.pose_position
        master_rig.data.pose_position = 'REST'
        # Force a scene update so modifiers see the rest pose
        context.view_layer.update()
        # --------------------------------------
        
        bpy.ops.object.select_all(action='DESELECT')
        to_duplicate = []
        if master_rig.visible_get():
            master_rig.select_set(True)
            to_duplicate.append(master_rig)
            
        for child in master_rig.children_recursive:
            if child.visible_get():
                child.select_set(True)
                to_duplicate.append(child)

        if len(to_duplicate) <= 1:
            self.report({'ERROR'}, "No visible meshes found to bake!")
            return {'CANCELLED'}

        bpy.ops.object.duplicate()
        copies = context.selected_objects
        new_rig = next((obj for obj in copies if obj.type == 'ARMATURE'), None)
        
        if not new_rig:
            self.report({'ERROR'}, "Failed to clone the rig correctly.")
            return {'CANCELLED'}
            
        new_rig.name = f"{PREFIX}_{RIG_NAME}"

        new_col = bpy.data.collections.new(f"{PREFIX}_Collection")
        context.scene.collection.children.link(new_col)
        widget_col = bpy.data.collections.new(f"{PREFIX}_Rig_Widgets")
        new_col.children.link(widget_col)
        
        # Exclude widgets from view
        def exclude_collection(layer_col, target_name):
            for child in layer_col.children:
                if child.name == target_name:
                    child.exclude = True
                    return True
                if exclude_collection(child, target_name):
                    return True
            return False
        exclude_collection(context.view_layer.layer_collection, widget_col.name)
        
        # Bone Widgets
        widget_map = {}
        for bone in new_rig.pose.bones:
            widget_obj = bone.custom_shape
            if widget_obj:
                if widget_obj.name not in widget_map:
                    new_widget = widget_obj.copy()
                    new_widget.name = f"{PREFIX}_WGT_{widget_obj.name}"
                    new_widget.data = widget_obj.data.copy()
                    widget_col.objects.link(new_widget)
                    widget_map[widget_obj.name] = new_widget
                bone.custom_shape = widget_map[widget_obj.name]
                
        material_map = {} 

        for obj in copies:
            for col in obj.users_collection:
                col.objects.unlink(obj)
            new_col.objects.link(obj)

            if obj.type == 'MESH':
                context.view_layer.objects.active = obj
                obj.parent = new_rig
                mods_to_apply = [m.name for m in obj.modifiers if m.type != 'ARMATURE']
                for m_name in mods_to_apply:
                    try: bpy.ops.object.modifier_apply(modifier=m_name)
                    except: pass
                
                # 2. Universal Material Prefixing
                for slot in obj.material_slots:
                    if slot.material:
                        orig_mat = slot.material
                        
                        # Check if we already handled this material for another object 
                        # or another slot on the Body
                        if orig_mat not in material_map:
                            new_mat = orig_mat.copy()
                            # Apply the user's custom prefix from the UI
                            new_mat.name = f"{PREFIX}_{orig_mat.name}"
                            material_map[orig_mat] = new_mat
                        
                        # Assign the shared unique version
                        slot.material = material_map[orig_mat]
                
                arm_mod = next((m for m in obj.modifiers if m.type == 'ARMATURE'), None)
                if not arm_mod:
                    arm_mod = obj.modifiers.new(name="Armature", type='ARMATURE')
                arm_mod.object = new_rig
                
                clean_obj_name = obj.name.split(".")[0]
                obj.name = f"{PREFIX}_{clean_obj_name}"

        ### RECURSIVE SAFE CLEANUP ###
        orig_coll = bpy.data.collections.get("Master_Character_Collection")
        if orig_coll:
            # 1. Use a set to collect EVERY object in the collection AND its sub-collections
            all_objs = set()
            def get_all_children(col):
                for obj in col.objects:
                    all_objs.add(obj)
                for child_col in col.children:
                    get_all_children(child_col)
            
            get_all_children(orig_coll)
            
            # 2. Collect the data-blocks from every object found
            data_to_delete = {o.data for o in all_objs if o.data}

            # 3. Delete the Objects first
            for o in all_objs:
                try:
                    bpy.data.objects.remove(o, do_unlink=True)
                except:
                    pass
            
            # 4. Delete the Data-Blocks (This frees the names like "Body")
            for data in data_to_delete:
                try:
                    if data.users == 0:
                        if isinstance(data, bpy.types.Mesh):
                            bpy.data.meshes.remove(data)
                        elif isinstance(data, bpy.types.Armature):
                            bpy.data.armatures.remove(data)
                except:
                    pass

            # 5. Delete the main collection and all its sub-collections
            def delete_sub_collections(col):
                for child in col.children:
                    delete_sub_collections(child)
                bpy.data.collections.remove(col)
            
            delete_sub_collections(orig_coll)

        # 6. Final safety purge for materials/textures
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

        # This switches your NEW baked rig (with the prefix) to Pose Mode
        if new_rig:
            new_rig.data.pose_position = 'POSE'
            context.view_layer.objects.active = new_rig
            new_rig.select_set(True)
        context.view_layer.update()
        self.report({'INFO'}, f"Baked {PREFIX} successfully!")
        return {'FINISHED'} 

# --- 3. UI PANEL ---
class UI_PT_CharacterCustomizer(bpy.types.Panel):
    bl_label = "HyChar Customizer"
    bl_idname = "UI_PT_character_customizer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'HyChar'

    def gv(self, mat_prefix, grp, sock):
        obj = bpy.data.objects.get("Body")
        if not obj: return 0
        try:
            # Find the first slot where the material name starts with our prefix
            slot = next((s for s in obj.material_slots if s.material and s.material.name.startswith(mat_prefix)), None)
            if not slot: return 0
            
            node = slot.material.node_tree.nodes.get(grp)
            s = node.inputs.get(sock)
            for p in ["index", "value", "default_value"]:
                if hasattr(s, p): return getattr(s, p)
            return 0
        except: return 0

    def mat_ui(self, layout, mat_prefix, grp, sock, text=""):
        obj = bpy.data.objects.get("Body")
        if not obj: return
        try:
            # KEEPING YOUR LOGIC: Find slot where material name starts with prefix
            slot = next((s for s in obj.material_slots if s.material and s.material.name.startswith(mat_prefix)), None)
            if not slot: return
            
            node = slot.material.node_tree.nodes.get(grp)
            s = node.inputs.get(sock)
            prop = next((p for p in ["index", "value", "default_value", "enum_value"] if hasattr(s, p)), None)
            
            if prop:
                # This split forces the 0.4 label ratio to match standard dropdowns
                split = layout.split(factor=0.4)
                split.label(text=text if text else s.name)
                split.prop(s, prop, text="") # text="" prevents the double-label bug
        except: pass

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj1 = get_obj1()
        obj2 = get_obj2()
        obj3 = get_obj3()
        obj4 = get_obj4()
        obj5 = get_obj5()
        obj6 = get_obj6()
        obj7 = get_obj7()
        obj8 = get_obj8()
        obj9 = get_obj9()
        obj10 = get_obj10()
        obj11 = get_obj11()
        obj12 = get_obj12()
        main_rig = bpy.data.objects.get("CharRig")

        layout.operator("mesh.individual_bake", text="Bake Textures", icon='RENDER_STILL')
        # Create a sub-layout that is grayed out and indented
        sub = layout.column(align=True)
        sub.active = False  # Makes the text gray/subtle
        
        row = sub.row()
        row.label(text="", icon='BLANK1') # Empty icon/text for indentation
        row.scale_x = 0.2                  # Shrink this spacer for slight indent
        row.label(text="Finalizes Textures", icon='INFO')
        
        layout.separator()
        if not main_rig:
            col = layout.column(align=True)
            col.scale_y = 2.0
            col.operator("hychar.spawn_character", text="SPAWN CHARACTER", icon='APPEND_BLEND')
            return
            

        if not obj1 or not obj2:
            layout.label(text="Meshes missing!", icon='ERROR')
            return

        gn1 = obj1.modifiers.get("GeometryNodes")
        gn2 = obj2.modifiers.get("GeometryNodes")
        gn3 = obj3.modifiers.get("GeometryNodes")
        gn4 = obj4.modifiers.get("GeometryNodes")
        gn5 = obj5.modifiers.get("GeometryNodes")
        gn6 = obj6.modifiers.get("GeometryNodes")
        gn7 = obj7.modifiers.get("GeometryNodes")
        gn8 = obj8.modifiers.get("GeometryNodes")
        gn9 = obj9.modifiers.get("GeometryNodes")
        gn10 = obj10.modifiers.get("GeometryNodes")
        gn11 = obj11.modifiers.get("GeometryNodes")
        gn12 = obj12.modifiers.get("GeometryNodes")
        
        standard_materials = {
        "Faded Leather": "Faded Leather",
        "Jean Generic": "Jean Generic",
        "Colored Cotton": "Colored Cotton",
        "Ornamented Metal": "Ornamented Metal",
        "Fantasy Cotton": "Fantasy Cotton",
        "Dark Fantasy Cotton": "Dark Fantasy Cotton",
        "Pastel Cotton": "Pastel Cotton",
        "Rotten Fabric": "Rotten Fabric",
        "Flashy Synthetic": "Flashy Synthetic",
        "Shiny Fabric": "Shiny Fabric"
        }
        # --- GENERAL ---
        box = layout.box()
        box.prop(scene, "ui_show_general", text="GENERAL", 
                 icon='TRIA_DOWN' if scene.ui_show_general else 'TRIA_RIGHT', emboss=False)
        if scene.ui_show_general:
            col = box.column(align=True)
            self.mat_ui(col, "Body", "HyBody", "Body Type", text="Body Type")
            self.mat_ui(col, "Face", "HyFace", "Face Type", text="Face Type")
            split = col.split(factor=0.4)
            split.label(text="Skintone")
            
            split.prop(scene, "hy_skintone_master", text="")
            self.mat_ui(col, "Ears", "HyEars", "Ears", text="Ears")
            self.mat_ui(col, "Mouth", "HyMouth", "Mouth Type", text="Mouth")
            col.separator()
            col.label(text="EYES", icon='HIDE_OFF')
            self.mat_ui(col, "Eyes", "HyEyes", "Skin", text="Skin")
            self.mat_ui(col, "Eyes", "HyEyes", "Style", text="Style")
            self.mat_ui(col, "Eyes", "HyEyes", "Eye Color", text="  └ Color")
            col.separator()
            col.label(text="EYE WHITES", icon='SHADING_RENDERED')
            self.mat_ui(col, "EyeWhites", "HyEyeWhites", "Skin", text="Skin")
            self.mat_ui(col, "EyeWhites", "HyEyeWhites", "Style", text="Style")
            self.mat_ui(col, "EyeWhites", "HyEyeWhites", "Color", text="  └ Color")
            col.separator()
            col.label(text="UNDERWEAR", icon='MOD_CLOTH')
            self.mat_ui(col, "Underwear", "HyUnderwear", "Underwear", text="Underwear")
            self.mat_ui(col, "Underwear", "HyUnderwear", "Colored Cotton", text="  └ Color")

        # --- HEAD ---
        box = layout.box()
        box.prop(scene, "ui_show_head", text="HEAD", 
                 icon='TRIA_DOWN' if scene.ui_show_head else 'TRIA_RIGHT', emboss=False)
        if scene.ui_show_head:
            col = box.column(align=True)
            split = col.split(factor=0.4)
            split.label(text="Hair")
            split.prop(gn6, '["Socket_2"]', text="")
            self.mat_ui(col, "Hair", "HyHair", "Hair Color", text="  └ Color")
            col.separator()
            self.mat_ui(col, "Eyebrows", "HyEyebrows", "Eyebrows", text="Eyebrows")
            self.mat_ui(col, "Eyebrows", "HyEyebrows", "Brow Color", text="  └ Brow Color")
            col.separator()
            split = col.split(factor=0.4)
            split.label(text="Beard")
            split.prop(gn1, '["Socket_4"]', text="")
            self.mat_ui(col, "Beard", "HyBeard", "Beard Color", text="  └ Color")

        # --- ACCESSORIES ---
        box = layout.box()
        box.prop(scene, "ui_show_acc", text="ACCESSORIES", 
                 icon='TRIA_DOWN' if scene.ui_show_acc else 'TRIA_RIGHT', emboss=False)
        if scene.ui_show_acc:
            col = box.column(align=True)
            
            split = col.split(factor=0.4)
            split.label(text="Head Accessory")
            split.prop(gn7, '["Socket_22"]', text="")
            self.mat_ui(col, "HeadAcc", "HyHeadAcc", "Material Selection", text="  └ Material")
            val_head = self.gv("HeadAcc", "HyHeadAcc", "Material Selection")
            if val_head in standard_materials:
                self.mat_ui(col.column(align=True), "HeadAcc", "HyHeadAcc", standard_materials[val_head], text="      └ Color")
                
            col.separator()
            
            split = col.split(factor=0.4)
            split.label(text="Face Accessory")
            split.prop(gn4, '["Socket_21"]', text="")
            self.mat_ui(col, "FaceAcc", "HyFaceAcc", "Material Selection", text="  └ Material")
            val_face = self.gv("FaceAcc", "HyFaceAcc", "Material Selection")
            if val_face in standard_materials:
                self.mat_ui(col.column(align=True), "FaceAcc", "HyFaceAcc", standard_materials[val_face], text="      └ Color")
            col.separator()
            # --- Earrings Selection ---
            split = col.split(factor=0.4)
            split.label(text="Earrings")
            split.prop(gn3, '["Socket_19"]', text="")
            
            split = col.split(factor=0.4)
            split.label(text="Side")
            split.prop(gn3, '["Socket_20"]', text="")

            ear_choice = gn3["Socket_19"]
            # Map choice to the arguments needed by mat_ui
            # {index: (mat_prefix, grp, sock, label)}
            ear_map = {
                0: ("MetalEar", "HyMetalEar", "Ornamented Metal", "  └ Color"),
                1: ("MetalEar", "HyMetalEar", "Ornamented Metal", "  └ Color"),
                2: ("MetalEar", "HyMetalEar", "Ornamented Metal", "  └ Color"),
                3: ("HoopsEar", "HyHoopsEar", "Menu", "  └ Color"),
                4: ("MetalEar", "HyMetalEar", "Ornamented Metal", "  └ Color"),
                5: ("SpiralEar", "HySpiralEar", "Menu", "  └ Color")
            }

            if ear_choice in ear_map:
                m_prefix, g_name, s_name, ui_label = ear_map[ear_choice]
                # Now we use your helper function!
                self.mat_ui(col, m_prefix, g_name, s_name, text=ui_label)

        # --- BODY & CLOTHING ---
        box = layout.box()
        box.prop(scene, "ui_show_body", text="BODY & CLOTHING", 
                 icon='TRIA_DOWN' if scene.ui_show_body else 'TRIA_RIGHT', emboss=False)
        if scene.ui_show_body:
            col = box.column(align=True)

            # --- UNDERSHIRT ---
            col.label(text="UNDERSHIRT", icon='MOD_CLOTH')
            split = col.split(factor=0.4)
            split.label(text="Style")
            split.prop(gn12, '["Socket_4"]', text="")
            self.mat_ui(col, "Undershirt", "HyUndershirt", "Material Selection", text="  └ Material")
            val_utop = self.gv("Undershirt", "HyUndershirt", "Material Selection")
            if val_utop in standard_materials:
                self.mat_ui(col.column(align=True), "Undershirt", "HyUndershirt", standard_materials[val_utop], text="      └ Color")

            col.separator()

            # --- OVERSHIRT ---
            col.label(text="OVERSHIRT", icon='MOD_CLOTH')
            split = col.split(factor=0.4)
            split.label(text="Style")
            split.prop(gn9, '["Socket_4"]', text="")
            self.mat_ui(col, "Overshirt", "HyOvershirt", "Material Selection", text="  └ Material")
            val_over = self.gv("Overshirt", "HyOvershirt", "Material Selection")
            if val_over in standard_materials:
                self.mat_ui(col.column(align=True), "Overshirt", "HyOvershirt", standard_materials[val_over], text="      └ Color")
            
            col.separator()

            # --- GLOVES ---
            col.label(text="GLOVES", icon='MOD_CLOTH')
            split = col.split(factor=0.4)
            split.label(text="Style")
            split.prop(gn5, '["Socket_4"]', text="")
            self.mat_ui(col, "Gloves", "HyGloves", "Material Selection", text="  └ Material")
            val_glove = self.gv("Gloves", "HyGloves", "Material Selection")
            if val_glove in standard_materials:
                self.mat_ui(col.column(align=True), "Gloves", "HyGloves", standard_materials[val_glove], text="      └ Color")
            

            col.separator()

            # --- PANTS ---
            col.label(text="PANTS", icon='USER')
            split = col.split(factor=0.4)
            split.label(text="Style")
            split.prop(gn10, '["Socket_4"]', text="")
            self.mat_ui(col, "Pants", "HyPants", "Material Selection", text="  └ Material")
            val_pants = self.gv("Pants", "HyPants", "Material Selection")
            if val_pants in standard_materials:
                self.mat_ui(col.column(align=True), "Pants", "HyPants", standard_materials[val_pants], text="      └ Color")

            col.separator()

            # --- OVERPANTS ---
            col.label(text="OVERPANTS", icon='USER')
            split = col.split(factor=0.4)
            split.label(text="Style")
            split.prop(gn8, '["Socket_4"]', text="")
            self.mat_ui(col, "Overpants", "HyOverpants", "Material Selection", text="  └ Material")
            val_opants = self.gv("Overpants", "HyOverpants", "Material Selection")
            if val_opants in standard_materials:
                self.mat_ui(col.column(align=True), "Overpants", "HyOverpants", standard_materials[val_opants], text="      └ Color")

            col.separator()

            # --- SHOES ---
            col.label(text="SHOES", icon='MOD_DYNAMICPAINT')
            split = col.split(factor=0.4)
            split.label(text="Style")
            split.prop(gn11, '["Socket_15"]', text="")
            self.mat_ui(col, "Shoes", "HyShoes", "Material Selection", text="  └ Material")
            val_shoes = self.gv("Shoes", "HyShoes", "Material Selection")
            if val_shoes in standard_materials:
                self.mat_ui(col.column(align=True), "Shoes", "HyShoes", standard_materials[val_shoes], text="      └ Color")

        # --- CAPE (Skin 2 / HySkin02) ---
        box = layout.box()
        box.prop(scene, "ui_show_cape", text="CAPE", 
                 icon='TRIA_DOWN' if scene.ui_show_cape else 'TRIA_RIGHT', emboss=False)
        if scene.ui_show_cape:
            col = box.column(align=True)
            split = col.split(factor=0.4)
            split.label(text="Style")
            split.prop(gn2, '["Socket_17"]', text="")
            split = col.split(factor=0.4)
            split.label(text="Neck")
            split.prop(gn2, '["Socket_18"]', text="")
            self.mat_ui(col, "Cape", "HyCape", "Material Selection", text="  └ Material")
            val_cape = self.gv("Cape", "HyCape", "Material Selection")
            if val_cape in standard_materials:
                self.mat_ui(col.column(align=True), "Cape", "HyCape", standard_materials[val_cape], text="      └ Color")

        # --- FOOTER ---
        layout.separator(factor=2.0)
        export_box = layout.box()
        export_box.label(text="Finalize Character", icon='EXPORT')
        export_box.prop(scene, "custom_rig_prefix", text="Char Name:")
        
        export_box.operator("mesh.clone_factory_final", text="APPLY TO CHARACTER", icon='DUPLICATE')
        export_box.label(text="Note: Creates Single User Materials", icon='INFO')
        export_box.label(text="Colors Still Accessible in Shaders")
        layout.label(text="HyChar v1.0.5 | Created by DxF")

def update_hy_skintone(self, context):
    # Convert the slider integer to a string to avoid the Enum error
    val_str = str(self.hy_skintone_master)
    
    obj = bpy.data.objects.get("Body") or context.active_object
    if not obj or obj.type != 'MESH':
        return

    sync_map = {
        "Body": "HyBody",
        "Ears": "HyEars",
        "Mouth": "HyMouth",
        "Face": "HyFace"
    }

    for slot in obj.material_slots:
        if not slot.material or not slot.material.use_nodes:
            continue
            
        mat = slot.material
        for prefix, group_name in sync_map.items():
            if mat.name.startswith(prefix):
                node = mat.node_tree.nodes.get(group_name)
                if node:
                    sk_input = node.inputs.get("Skintone")
                    if not sk_input:
                        sk_input = node.inputs[0]
                        
                    if sk_input:
                        try:
                            # Try setting it as a string first (for Enums)
                            sk_input.default_value = val_str
                        except TypeError:
                            # Fallback to int if that specific socket actually is a number
                            sk_input.default_value = self.hy_skintone_master
    
    # Refresh viewport to show the change
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()
# --- 4. REGISTRATION ---
classes = (
    HYCHAR_OT_spawn_character, 
    MESH_OT_clone_factory_final, 
    UI_PT_CharacterCustomizer, 
    bake_logic.MESH_OT_individual_bake
)

def register():
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.ui_show_general = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.ui_show_head = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.ui_show_acc = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.ui_show_body = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.ui_show_cape = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.custom_rig_prefix = bpy.props.StringProperty(name="Prefix", default="NewChar")
    bpy.types.Scene.hy_skintone_master = bpy.props.IntProperty(
    name="Master Skintone",
    min=1,
    max=49,
    default=4,
    update=update_hy_skintone
    )

def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.ui_show_general
    del bpy.types.Scene.ui_show_head
    del bpy.types.Scene.ui_show_acc
    del bpy.types.Scene.ui_show_body
    del bpy.types.Scene.ui_show_cape
    del bpy.types.Scene.custom_rig_prefix
    del bpy.types.Scene.hy_skintone_master
    

if __name__ == "__main__":
    register()