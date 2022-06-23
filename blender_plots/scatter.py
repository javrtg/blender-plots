import numpy as np

import bpy
import blender_plots.blender_utils as bu

POINT_COLOR = "point_color"
MARKER_TYPES = {
    "cones": "GeometryNodeMeshCone",
    "cubes": "GeometryNodeMeshCube",
    "cylinders": "GeometryNodeMeshCylinder",
    "grids": "GeometryNodeMeshGrid",
    "ico_spheres": "GeometryNodeMeshIcoSphere",
    "circles": "GeometryNodeMeshCircle",
    "lines": "GeometryNodeMeshLine",
    "uv_spheres": "GeometryNodeMeshUVSphere",
}


class Scatter:
    """Create a scatterplot.

    Args:
        points: Nx3 array with xyz positions for points to scatter
        color: Nx3 array with rgb values for each point, or a single rgb-value (e.g. (1, 0, 0) for red) to apply to
            every point.
        name: name to use for blender object. Will delete any previous plot with the same name.
        marker_type: select appearance of points. Either MARKER_TYPE, "spheres", bpy_types.Mesh or bpy_types.Object
        marker_scale: xyz scale for markers
        marker_kwargs: additional arguments for configuring markers
    """

    def __init__(self, points, color=None, name="scatter", marker_type="cubes", marker_scale=None,
                 randomize_rotation=False, **marker_kwargs):
        self.name = name
        self.base_object = None
        self.mesh = None
        self.color_material = None

        self.points = points
        if marker_type == "spheres":
            self.points_modifier = add_sphere_markers(self.base_object, **marker_kwargs)
        else:
            self.points_modifier = add_mesh_markers(self.base_object, randomize_rotation=randomize_rotation,
                                                    marker_type=marker_type, marker_scale=marker_scale, **marker_kwargs)
        self.color = color

    @property
    def points(self):
        return self._points

    @points.setter
    def points(self, points):
        self._points = points
        self.update_points()

    def update_points(self):
        if self.mesh is None:
            self.mesh = bpy.data.meshes.new(self.name)
            self.mesh.from_pydata(self._points, [], [])
        else:
            self.mesh.vertices.foreach_set("co", self._points.reshape(-1))

        if self.base_object is None:
            self.base_object = bu.new_empty(self.name, self.mesh)
        else:
            self.base_object.data = self.mesh
        self.mesh.update()

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, color):
        self._color = color
        self.update_color()

    def update_color(self):
        if self._color is not None:
            set_vertex_colors(self.mesh, self.color)
            self.color_material = get_vertex_color_material()
            self.mesh.materials.append(self.color_material)
            self.points_modifier["Input_2"] = self.color_material


def set_vertex_colors(mesh, color):
    """Add a point_color attribute to each vertex in the mesh with values given by `color`"""
    if np.array(color).ndim == 1:
        color = np.tile(color, (len(mesh.vertices), 1))
    if color.shape[1] == 3:
        color = np.hstack([color, np.ones((len(color), 1))])
    elif not color.shape[1] == 4:
        raise ValueError(f"Invalid color array shape {color.shape}, expectex Nx3 or Nx4")
    if len(mesh.vertices) != len(color):
        raise ValueError(f"Got {len(mesh.vertices)} vertices and {len(color)} color values")

    if POINT_COLOR not in mesh.attributes:
        mesh.attributes.new(name=POINT_COLOR, type="FLOAT_COLOR", domain="POINT")
    mesh.attributes[POINT_COLOR].data.foreach_set("color", color.reshape(-1))


def get_vertex_color_material():
    """Create a material that obtains its color from the point_color attribute"""
    material = bpy.data.materials.new("color")
    material.use_nodes = True
    color_node = material.node_tree.nodes.new("ShaderNodeAttribute")
    color_node.attribute_name = POINT_COLOR

    material.node_tree.links.new(color_node.outputs["Color"],
                                 material.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    return material


def add_mesh_markers(base_object, marker_type, randomize_rotation=False, marker_scale=None, **marker_kwargs):
    """Create a geometry node modifier that instances a mesh on each vertex.
    Args:
        base_object: object containing mesh with vertices to instance on.
        marker_type: name of marker type (see MARKER_TYPES), or a blender mesh/object to use as marker
        randomize_rotation: if True each mesh instance will be given a random rotation (uniform euler angles)
        marker_scale: xyz scale for markers
        marker_kwargs: additional arguments for configuring markers
    """
    modifier = base_object.modifiers.new(type="NODES", name="spheres")
    node_linker = bu.NodeLinker(modifier.node_group)
    modifier.node_group.inputs.new("NodeSocketMaterial", "Point Color")  # Input_2

    points_socket = node_linker.new_node(
        "GeometryNodeMeshToPoints",
        mesh=node_linker.group_input.outputs["Geometry"]
    ).outputs["Points"]

    if marker_type in MARKER_TYPES:
        mesh_socket = node_linker.new_node(node_type=MARKER_TYPES[marker_type], **marker_kwargs).outputs["Mesh"]
    elif isinstance(marker_type, bpy.types.Mesh) or isinstance(marker_type, bpy.types.Object):
        # use the supplied mesh by adding it as an input socket to the modifier
        modifier.node_group.inputs.new("NodeSocketObject", "Point Instance")  # Input_3
        modifier["Input_3"] = marker_type
        modifier.show_viewport = False
        modifier.show_viewport = True
        mesh_socket = node_linker.new_node(
            "GeometryNodeObjectInfo",
            Object=node_linker.group_input.outputs["Point Instance"]
        ).outputs["Geometry"]
    else:
        raise TypeError(f"Invalid marker type: {marker_type}, expected bpy.types.Mesh, bpy.Types.Object, "
                        f"or one of: {', '.join(MARKER_TYPES)}")

    colored_mesh = node_linker.new_node(
        "GeometryNodeSetMaterial",
        geometry=mesh_socket,
        material=node_linker.group_input.outputs["Point Color"]
    ).outputs["Geometry"]
    node = node_linker.new_node(
        "GeometryNodeInstanceOnPoints",
        points=points_socket,
        instance=colored_mesh,
        scale=marker_scale if marker_scale is not None else [1, 1, 1]
    )
    if randomize_rotation:
        # these rotation are not uniform (some orientations will be more likely than others)
        # but it usually looks decent
        random_euler = node_linker.new_node("FunctionNodeRandomValue", max=(180, 180, 180))
        random_euler.data_type = "FLOAT_VECTOR"
        node_linker.link(random_euler.outputs["Value"], node.inputs["Rotation"])

    node = node_linker.new_node("GeometryNodeRealizeInstances", geometry=node.outputs["Instances"])
    node_linker.new_node("NodeGroupOutput", geometry=node.outputs["Geometry"])
    return modifier


def add_sphere_markers(base_object, **marker_kwargs):
    """Create a geometry node modifier that adds a point on each vertex. This will result in perfect spheres, only
        visible in rendered view with rendering engine set to `Cycles`
    Args:
        base_object: object containing mesh with vertices to instance on.
        marker_kwargs: arguments to passed to node_linker.new_node when generating point node. e.g. radius=0.1
    """
    modifier = base_object.modifiers.new(type="NODES", name="spheres")
    node_linker = bu.NodeLinker(modifier.node_group)
    modifier.node_group.inputs.new("NodeSocketMaterial", "Point Color")  # Input_2

    points = node_linker.new_node(
        "GeometryNodeMeshToPoints",
        mesh=node_linker.group_input.outputs["Geometry"],
        **marker_kwargs,
    ).outputs["Points"]
    node = node_linker.new_node(
        "GeometryNodeSetMaterial",
        geometry=points,
        material=node_linker.group_input.outputs["Point Color"]
    )
    node_linker.new_node("NodeGroupOutput", geometry=node.outputs["Geometry"])
    return modifier
