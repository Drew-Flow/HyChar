import bpy
import os

ADDON_DIR = os.path.dirname(__file__)
LIB_PATH = os.path.join(ADDON_DIR, "resources", "CharLibrary.blend")

# --- HELPER FUNCTIONS ---
def get_obj1():
    return next((o for o in bpy.data.objects if o.name.startswith("CharCust_1")), None)

def get_obj2():
    return next((o for o in bpy.data.objects if o.name.startswith("CharCust_2")), None)

# --- 1. SPAWN OPERATOR ---
class HYCHAR_OT_spawn_character(bpy.types.Operator):
    bl_idname = "hychar.spawn_character"
    bl_label = "Spawn Character"
    bl_description = "Appends character from the internal addon library folder"

    def execute(self, context):
        addon_dir = os.path.dirname(__file__)
        filepath = os.path.join(addon_dir, "resources", "CharLibrary.blend")
        
        if not os.path.exists(filepath):
            self.report({'ERROR'}, f"Library missing at: {filepath}")
            return {'CANCELLED'}

        coll_name = "Master_Character_Collection"

        with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
            if coll_name in data_from.collections:
                data_to.collections = [coll_name]
        
        for coll in data_to.collections:
            if coll:
                context.scene.collection.children.link(coll)
                
        self.report({'INFO'}, "Character Spawned!")
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
            
        new_rig.name = f"{PREFIX}_{RIG_NAME}_BAKED"

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
                
        target_mats = ["Skin", "Skin 2", "Earrings"]
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
                
                for slot in obj.material_slots:
                    if slot.material:
                        base_mat_name = slot.material.name.split(".")[0]
                        if base_mat_name in target_mats:
                            if base_mat_name not in material_map:
                                new_mat = slot.material.copy()
                                new_mat.name = f"{PREFIX}_{base_mat_name}"
                                material_map[base_mat_name] = new_mat
                            slot.material = material_map[base_mat_name]
                
                arm_mod = next((m for m in obj.modifiers if m.type == 'ARMATURE'), None)
                if not arm_mod:
                    arm_mod = obj.modifiers.new(name="Armature", type='ARMATURE')
                arm_mod.object = new_rig
                
                clean_obj_name = obj.name.split(".")[0]
                obj.name = f"{PREFIX}_{clean_obj_name}_BAKED"

        orig_coll = bpy.data.collections.get("Master_Character_Collection")
        if orig_coll:
            objs_to_delete = [o for o in orig_coll.objects]
            for o in objs_to_delete:
                bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(orig_coll)
        
        self.report({'INFO'}, f"Baked {PREFIX} successfully! Customizer reset.")
        return {'FINISHED'}

# --- 3. UI PANEL ---
class UI_PT_CharacterCustomizer(bpy.types.Panel):
    bl_label = "HyChar Customizer"
    bl_idname = "UI_PT_character_customizer"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'HyChar'

    def gv(self, mat_prefix, grp, sock):
        obj = get_obj1()
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
        obj = get_obj1()
        if not obj: return
        try:
            # Find the first slot where the material name starts with our prefix
            slot = next((s for s in obj.material_slots if s.material and s.material.name.startswith(mat_prefix)), None)
            if not slot: return
            
            node = slot.material.node_tree.nodes.get(grp)
            s = node.inputs.get(sock)
            prop = next((p for p in ["index", "value", "default_value", "enum_value"] if hasattr(s, p)), None)
            if prop: layout.prop(s, prop, text=text if text else s.name)
        except: pass

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        obj1 = get_obj1()
        obj2 = get_obj2()
        main_rig = bpy.data.objects.get("CharRig")

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

        # --- GENERAL ---
        box = layout.box()
        box.prop(scene, "ui_show_general", text="GENERAL", 
                 icon='TRIA_DOWN' if scene.ui_show_general else 'TRIA_RIGHT', emboss=False)
        if scene.ui_show_general:
            col = box.column(align=True)
            self.mat_ui(col, "Skin", "HySkin01", "Body Type", text="Body Type")
            self.mat_ui(col, "Skin", "HySkin01", "Face Type", text="Face Type")
            self.mat_ui(col, "Skin", "HySkin01", "Skintone", text="Skintone")
            self.mat_ui(col, "Skin", "HySkin01", "Ears", text="Ears")
            self.mat_ui(col, "Skin", "HySkin01", "Mouth Type", text="Mouth")
            col.separator()
            col.label(text="EYES", icon='HIDE_OFF')
            self.mat_ui(col, "Skin", "HySkin01", "Socket_17", text="Skin")
            self.mat_ui(col, "Skin", "HySkin01", "Socket_18", text="Style")
            self.mat_ui(col, "Skin", "HySkin01", "Socket_19", text="  └ Color")
            col.separator()
            col.label(text="EYE WHITES", icon='SHADING_RENDERED')
            self.mat_ui(col, "Skin", "HySkin01", "Socket_25", text="Skin")
            self.mat_ui(col, "Skin", "HySkin01", "Socket_26", text="Style")
            self.mat_ui(col, "Skin", "HySkin01", "Socket_27", text="  └ Color")
            col.separator()
            col.label(text="UNDERWEAR", icon='MOD_CLOTH')
            self.mat_ui(col, "Skin", "HySkin01", "Socket_98", text="Underwear")
            self.mat_ui(col, "Skin", "HySkin01", "Socket_99", text="  └ Color")

        # --- HEAD ---
        box = layout.box()
        box.prop(scene, "ui_show_head", text="HEAD", 
                 icon='TRIA_DOWN' if scene.ui_show_head else 'TRIA_RIGHT', emboss=False)
        if scene.ui_show_head:
            col = box.column(align=True)
            col.prop(gn1, '["Socket_2"]', text="Hair Style")
            self.mat_ui(col, "Skin", "HySkin01", "Hair Color", text="  └ Color")
            col.separator()
            self.mat_ui(col, "Skin", "HySkin01", "Socket_14", text="Eyebrows")
            self.mat_ui(col, "Skin", "HySkin01", "Socket_15", text="  └ Brow Color")
            col.separator()
            col.prop(gn1, '["Socket_4"]', text="Beard Style")
            self.mat_ui(col, "Skin", "HySkin01", "Beard Color", text="  └ Color")

        # --- ACCESSORIES ---
        box = layout.box()
        box.prop(scene, "ui_show_acc", text="ACCESSORIES", 
                 icon='TRIA_DOWN' if scene.ui_show_acc else 'TRIA_RIGHT', emboss=False)
        if scene.ui_show_acc:
            col = box.column(align=True)
            col.prop(gn2, '["Socket_22"]', text="Head Accessory")
            self.mat_ui(col, "Skin 2", "HySkin02", "Socket_50", text="  └ Material")
            val_head = self.gv("Skin 2", "HySkin02", "Socket_50")
            head_slots = {"Faded Leather": "Socket_51", "Jean Generic": "Socket_52", "Colored Cotton": "Socket_53", "Ornamented Metal": "Socket_54", "Fantasy Cotton": "Socket_55", "Dark Fantasy Cotton": "Socket_56", "Pastel Cotton": "Socket_57", "Rotten Fabric": "Socket_58", "Flashy Synthetic": "Socket_59", "Shiny Fabric": "Socket_60"}
            if val_head in head_slots:
                self.mat_ui(col.column(align=True), "Skin 2", "HySkin02", head_slots[val_head], text="      └ Color")
            col.separator()
            col.prop(gn2, '["Socket_21"]', text="Face Accessory")
            self.mat_ui(col, "Skin 2", "HySkin02", "Socket_38", text="  └ Material")
            val_face = self.gv("Skin 2", "HySkin02", "Socket_38")
            face_slots = {"Faded Leather": "Socket_39", "Jean Generic": "Socket_40", "Colored Cotton": "Socket_41", "Ornamented Metal": "Socket_42", "Fantasy Cotton": "Socket_43", "Dark Fantasy Cotton": "Socket_44", "Pastel Cotton": "Socket_45", "Rotten Fabric": "Socket_46", "Flashy Synthetic": "Socket_47", "Shiny Fabric": "Socket_48"}
            if val_face in face_slots:
                self.mat_ui(col.column(align=True), "Skin 2", "HySkin02", face_slots[val_face], text="      └ Color")
            col.separator()
            col.prop(gn2, '["Socket_19"]', text="Earrings")
            col.prop(gn2, '["Socket_20"]', text="Side")
            ear_choice = gn2["Socket_19"]
            ear_mats = {1: "Ornamented Metal", 2: "Ornamented Metal", 3: "Color", 4: "Ornamented Metal", 5: "Color2"}
            if ear_choice in ear_mats:
                try:
                    mat_ear = obj2.material_slots["Earrings"].material
                    sock_ear = mat_ear.node_tree.nodes["HySkin03"].inputs.get(ear_mats[ear_choice])
                    if sock_ear: col.prop(sock_ear, "default_value", text="  └ Color Tint")
                except: pass

        # --- BODY & CLOTHING ---
        box = layout.box()
        box.prop(scene, "ui_show_body", text="BODY & CLOTHING", 
                 icon='TRIA_DOWN' if scene.ui_show_body else 'TRIA_RIGHT', emboss=False)
        if scene.ui_show_body:
            col = box.column(align=True)

            # --- UNDERTOP (Skin 1 / HySkin01) ---
            col.label(text="UNDERTOP", icon='MOD_CLOTH')
            col.prop(gn1, '["Socket_13"]', text="Style")
            self.mat_ui(col, "Skin", "HySkin01", "Socket_87", text="  └ Material Selection")
            val_utop = self.gv("Skin", "HySkin01", "Socket_87")
            utop_map = {"Faded Leather": "Socket_88", "Jean Generic": "Socket_89", "Colored Cotton": "Socket_90", "Ornamented Metal": "Socket_91", "Fantasy Cotton": "Socket_92", "Dark Fantasy Cotton": "Socket_93", "Pastel Cotton": "Socket_94", "Rotten Fabric": "Socket_95", "Flashy Synthetic": "Socket_96", "Shiny Fabric": "Socket_97"}
            if val_utop in utop_map:
                self.mat_ui(col.column(align=True), "Skin", "HySkin01", utop_map[val_utop], text="      └ Color")

            col.separator()

            # --- OVERSHIRT (Skin 1 / HySkin01) ---
            col.label(text="OVERSHIRT", icon='MOD_CLOTH')
            # Check your GN modifier for the Glove Toggle Socket - often Socket_14
            col.prop(gn1, '["Socket_14"]', text="Style") 
            self.mat_ui(col, "Skin 2", "HySkin02", "Socket_2", text="  └ Material Selection")
            val_over = self.gv("Skin 2", "HySkin02", "Socket_2")
            over_map = {"Faded Leather": "Socket_3", "Jean Generic": "Socket_4", "Colored Cotton": "Socket_5", "Ornamented Metal": "Socket_6", "Fantasy Cotton": "Socket_7", "Dark Fantasy Cotton": "Socket_8", "Pastel Cotton": "Socket_9", "Rotten Fabric": "Socket_10", "Flashy Synthetic": "Socket_11", "Shiny Fabric": "Socket_12"}
            if val_over in over_map:
                self.mat_ui(col.column(align=True), "Skin 2", "HySkin02", over_map[val_over], text="      └ Color")
            
            col.separator()

            # --- GLOVES (Skin 2 / HySkin02) ---
            col.label(text="GLOVES", icon='MOD_CLOTH')
            col.prop(gn1, '["Socket_12"]', text="Style")
            self.mat_ui(col, "Skin", "HySkin01", "Socket_75", text="  └ Material Selection")
            val_glove = self.gv("Skin", "HySkin01", "Socket_75")
            glove_map = {"Faded Leather": "Socket_76", "Jean Generic": "Socket_77", "Colored Cotton": "Socket_78", "Ornamented Metal": "Socket_79", "Fantasy Cotton": "Socket_80", "Dark Fantasy Cotton": "Socket_81", "Pastel Cotton": "Socket_82", "Rotten Fabric": "Socket_83", "Flashy Synthetic": "Socket_84", "Shiny Fabric": "Socket_85"}
            if val_glove in glove_map:
                self.mat_ui(col.column(align=True), "Skin", "HySkin01", glove_map[val_glove], text="      └ Color")
            

            col.separator()

            # --- PANTS (Skin 1 / HySkin01) ---
            col.label(text="PANTS", icon='USER')
            col.prop(gn1, '["Socket_5"]', text="Style")
            self.mat_ui(col, "Skin", "HySkin01", "Socket_46", text="  └ Material Selection")
            val_pants = self.gv("Skin", "HySkin01", "Socket_46")
            pants_map = {"Faded Leather": "Socket_47", "Jean Generic": "Socket_48", "Colored Cotton": "Socket_49", "Ornamented Metal": "Socket_50", "Fantasy Cotton": "Socket_51", "Dark Fantasy Cotton": "Socket_52", "Pastel Cotton": "Socket_53", "Rotten Fabric": "Socket_54", "Flashy Synthetic": "Socket_55", "Shiny Fabric": "Socket_56"}
            if val_pants in pants_map:
                self.mat_ui(col.column(align=True), "Skin", "HySkin01", pants_map[val_pants], text="      └ Color")

            col.separator()

            # --- OVERPANTS (Skin 1 / HySkin01) ---
            col.label(text="OVERPANTS", icon='USER')
            col.prop(gn1, '["Socket_11"]', text="Style")
            self.mat_ui(col, "Skin", "HySkin01", "Socket_57", text="  └ Material Selection")
            val_opants = self.gv("Skin", "HySkin01", "Socket_57")
            opants_map = {"Faded Leather": "Socket_58", "Jean Generic": "Socket_59", "Colored Cotton": "Socket_60", "Ornamented Metal": "Socket_61", "Fantasy Cotton": "Socket_62", "Dark Fantasy Cotton": "Socket_63", "Pastel Cotton": "Socket_64", "Rotten Fabric": "Socket_65", "Flashy Synthetic": "Socket_66", "Shiny Fabric": "Socket_67"}
            if val_opants in opants_map:
                self.mat_ui(col.column(align=True), "Skin", "HySkin01", opants_map[val_opants], text="      └ Color")

            col.separator()

            # --- SHOES (Skin 2 / HySkin02) ---
            col.label(text="SHOES", icon='MOD_DYNAMICPAINT')
            col.prop(gn2, '["Socket_15"]', text="Style")
            self.mat_ui(col, "Skin 2", "HySkin02", "Socket_14", text="  └ Material Selection")
            val_shoes = self.gv("Skin 2", "HySkin02", "Socket_14")
            shoe_map = {"Faded Leather": "Socket_15", "Jean Generic": "Socket_16", "Colored Cotton": "Socket_17", "Ornamented Metal": "Socket_18", "Fantasy Cotton": "Socket_19", "Dark Fantasy Cotton": "Socket_20", "Pastel Cotton": "Socket_21", "Rotten Fabric": "Socket_22", "Flashy Synthetic": "Socket_23", "Shiny Fabric": "Socket_24"}
            if val_shoes in shoe_map:
                self.mat_ui(col.column(align=True), "Skin 2", "HySkin02", shoe_map[val_shoes], text="      └ Color")

        # --- CAPE (Skin 2 / HySkin02) ---
        box = layout.box()
        box.prop(scene, "ui_show_cape", text="CAPE", 
                 icon='TRIA_DOWN' if scene.ui_show_cape else 'TRIA_RIGHT', emboss=False)
        if scene.ui_show_cape:
            col = box.column(align=True)
            col.prop(gn2, '["Socket_17"]', text="Style")
            col.prop(gn2, '["Socket_18"]', text="Neck")
            self.mat_ui(col, "Skin 2", "HySkin02", "Socket_25", text="  └ Material Selection")
            val_cape = self.gv("Skin 2", "HySkin02", "Socket_25")
            cape_map = {"Faded Leather": "Socket_26", "Jean Generic": "Socket_27", "Colored Cotton": "Socket_28", "Ornamented Metal": "Socket_29", "Fantasy Cotton": "Socket_30", "Dark Fantasy Cotton": "Socket_31", "Pastel Cotton": "Socket_32", "Rotten Fabric": "Socket_33", "Flashy Synthetic": "Socket_34", "Shiny Fabric": "Socket_35"}
            if val_cape in cape_map:
                self.mat_ui(col.column(align=True), "Skin 2", "HySkin02", cape_map[val_cape], text="      └ Color")

        # --- FOOTER ---
        layout.separator(factor=2.0)
        export_box = layout.box()
        export_box.label(text="Export Final Character", icon='EXPORT')
        export_box.prop(scene, "custom_rig_prefix", text="Rig Prefix")
        export_box.label(text="Note: Bake resets rig to Rest Pose", icon='INFO')
        export_box.operator("mesh.clone_factory_final", text="BAKE FULL CHARACTER", icon='DUPLICATE')
        layout.label(text="HyChar v1.0 | Created by DxF")

# --- 4. REGISTRATION ---
classes = (HYCHAR_OT_spawn_character, MESH_OT_clone_factory_final, UI_PT_CharacterCustomizer)

def register():
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.ui_show_general = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.ui_show_head = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.ui_show_acc = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.ui_show_body = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.ui_show_cape = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.custom_rig_prefix = bpy.props.StringProperty(name="Prefix", default="NewChar")

def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.Scene.ui_show_general
    del bpy.types.Scene.ui_show_head
    del bpy.types.Scene.ui_show_acc
    del bpy.types.Scene.ui_show_body
    del bpy.types.Scene.ui_show_cape
    del bpy.types.Scene.custom_rig_prefix

if __name__ == "__main__":
    register()