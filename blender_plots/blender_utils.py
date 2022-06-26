import bpy


class NodeLinker:
    """Wrapper for bpy.types.GeometryNodeTree which simplifies creating large node trees."""
    def __init__(self, node_group):
        self.node_group = node_group

    def new_node(self, node_type, **kwargs):
        """Adds a new node to the node group

        Args:
            node_type: type of node to add (e.g. GeometryNodeInstanceOnPoints) - to find available names you can either
                hover over the node name when adding one through the node editor, or check the `bl_idname`
                property of a node in python.
            kwargs: arguments in one of the following forms:
                input_socket_name=node_socket: will connect the supplied node_socket to the input socket
                    (e.g. mesh=node_group["Group Input"].outputs["Geometry"] for GeometryNodeMeshToPoints)
                input_socket_name=value: set the value of input socket (e.g. size=(5, 1, 1) for GeometryNodeMeshCube).
                input_i=value: set input i of node to value, useful in case multiple inputs have the same name.
        """
        if node_type == "NodeGroupOutput":
            # can only have one group output
            node = self.node_group.nodes["Group Output"]
        else:
            node = self.node_group.nodes.new(node_type)

        for key, value in kwargs.items():
            if value is not None:
                match key.split("_"):
                    case ["input", i] if i.isdigit():
                        blender_key = int(i)
                    case _:
                        blender_key = python_arg_to_blender_key(key)
                if isinstance(value, bpy.types.NodeSocket):
                    self.link(value, node.inputs[blender_key])
                elif isinstance(blender_key, int) or blender_key in node.inputs:
                    node.inputs[blender_key].default_value = value
                elif hasattr(node, key):
                    setattr(node, key, value)
                else:
                    raise ValueError(f"Node {node} has no attribute {key} or input {blender_key}.")
        return node

    def link(self, from_socket, to_socket):
        self.node_group.links.new(from_socket, to_socket)

    def new_input(self, input_type, input_name):
        self.node_group.inputs.new(input_type, input_name)

    @property
    def group_input(self):
        """Add input which can be accessed through modifiers panel."""
        return self.node_group.nodes["Group Input"]


def delete(obj, with_children=False):
    """Delete blender object and its children"""
    if with_children:
        for child in obj.children:
            delete(child, with_children=True)
    bpy.data.objects.remove(obj, do_unlink=True)


def new_empty(name, object_data=None, select=True):
    """Create new empty blender object with specified name and data, deletes any previous object with the same name."""
    if name in bpy.data.objects:
        delete(bpy.data.objects[name], with_children=True)

    new_object = bpy.data.objects.new(name, object_data)
    bpy.context.collection.objects.link(new_object)

    if select:
        bpy.context.view_layer.objects.active = new_object

    return new_object


def python_arg_to_blender_key(arg):
    """convert python argument to geometry node name, e.g. radius->Radius, instance_index->Instance Index"""
    return ' '.join([s.capitalize() for s in arg.split('_')])
