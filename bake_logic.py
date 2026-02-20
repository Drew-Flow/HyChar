import bpy
import os

class MESH_OT_individual_bake(bpy.types.Operator):
    """Bake Individual - 512px, Closest Filtering, Restored UDIM Logic"""
    bl_idname = "mesh.individual_bake"
    bl_label = "Bake Individual"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objs = [
            obj for obj in context.selected_objects 
            if obj.type == 'MESH' and not obj.name.split('.')[0].endswith(("Mouth", "Ears"))
        ]
        
        if not selected_objs:
            self.report({'WARNING'}, "No valid mesh objects selected (Mouth meshes excluded).")
            return {'CANCELLED'}
        
        addon_dir = os.path.dirname(os.path.dirname(__file__))
        lib_dir = os.path.join(addon_dir, "library", "baked_textures")
        if not os.path.exists(lib_dir):
            os.makedirs(lib_dir)

        for obj in selected_objs:
            # DESELECT ALL AND SELECT ONLY THIS MESH
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='OBJECT')
            context.scene.render.engine = 'CYCLES'
            context.scene.cycles.samples = 1
            
            # 1. UDIM TILE CALCULATION
            original_uv = obj.data.uv_layers.active
            if not original_uv: continue
            u_offset = int(min(d.uv[0] for d in original_uv.data))
            v_offset = int(min(d.uv[1] for d in original_uv.data))
            tile_num = 1001 + u_offset + (v_offset * 10)

            # 2. TARGET IMAGE (Set to 512x512)
            temp_name = f"Bake_{obj.name}_{tile_num}"
            bake_img = bpy.data.images.new(temp_name, 512, 512, alpha=True)

            # 3. TEMP BAKE UV (Shifted for Target)
            bake_uv = obj.data.uv_layers.new(name="TEMP_BAKEOFFSET")
            for i in range(len(bake_uv.data)):
                bake_uv.data[i].uv[0] = original_uv.data[i].uv[0] - u_offset
                bake_uv.data[i].uv[1] = original_uv.data[i].uv[1] - v_offset
            obj.data.uv_layers.active = bake_uv

            if obj.material_slots and obj.material_slots[0].material:
                mat = obj.material_slots[0].material
                mat.use_nodes = True
                nodes, links = mat.node_tree.nodes, mat.node_tree.links
                
                # SHADER LOCK: Force sources to use original coordinates
                uv_src_node = nodes.new('ShaderNodeUVMap')
                uv_src_node.uv_map = original_uv.name
                for node in nodes:
                    if node.type == 'TEX_IMAGE' and node.image and node.image.source == 'TILED':
                        links.new(uv_src_node.outputs['UV'], node.inputs['Vector'])

                target = nodes.new('ShaderNodeTexImage')
                target.image = bake_img
                nodes.active = target

                try:
                    # PERFORM BAKE
                    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, margin=2, use_clear=True)
                    
                    file_path = os.path.join(lib_dir, f"{obj.name}_{tile_num}.png")
                    bake_img.filepath_raw = file_path
                    bake_img.file_format = 'PNG'
                    bake_img.save()
                    
                    # 5. SHIFT ORIGINAL UVS TO 0-1 SPACE
                    for i in range(len(original_uv.data)):
                        original_uv.data[i].uv[0] -= u_offset
                        original_uv.data[i].uv[1] -= v_offset
                    
                    # 4. BUILD THE DIFFUSE / MIX / TRANSPARENT CHAIN
                    res_node = nodes.new('ShaderNodeTexImage')
                    res_node.name = "BAKED_RESULT"
                    res_node.image = bpy.data.images.load(file_path)
                    
                    # SET INTERPOLATION TO CLOSEST
                    res_node.interpolation = 'Closest'
                    res_node.extension = 'CLIP'
                    
                    diffuse = nodes.new('ShaderNodeBsdfDiffuse')
                    transparent = nodes.new('ShaderNodeBsdfTransparent')
                    mix = nodes.new('ShaderNodeMixShader')
                    output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), nodes.new('ShaderNodeOutputMaterial'))

                    # Linking logic
                    links.new(res_node.outputs['Color'], diffuse.inputs['Color'])
                    links.new(res_node.outputs['Alpha'], mix.inputs['Factor'])
                    links.new(transparent.outputs['BSDF'], mix.inputs[1])
                    links.new(diffuse.outputs['BSDF'], mix.inputs[2])
                    links.new(mix.outputs['Shader'], output.inputs['Surface'])

                finally:
                    # RESTORE
                    if "TEMP_BAKEOFFSET" in obj.data.uv_layers:
                        obj.data.uv_layers.remove(bake_uv)
                    obj.data.uv_layers.active = original_uv
                    nodes.remove(uv_src_node)
                    nodes.remove(target)
                    if bake_img.users == 0:
                        bpy.data.images.remove(bake_img)

        return {'FINISHED'}