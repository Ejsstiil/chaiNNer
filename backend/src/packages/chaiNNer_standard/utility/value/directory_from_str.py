from __future__ import annotations

from nodes.properties.inputs import DirectoryInput, TextInput
from nodes.properties.outputs import DirectoryOutput

from .. import value_group


@value_group.register(
    schema_id="chainner:utility:directory_fromstr",
    name="Directory from string",
    description="Outputs the given directory from given string.",
    icon="BsFolder",
    inputs=[
        TextInput("Path", min_length=0, hide_label=True, allow_empty_string=True),
    ],
    outputs=[
        DirectoryOutput("Directory", output_type="""
            match Input0 {
                string as path => Directory { path: path },
                _ => never
            }
        """),
    ],
)
def directory_node(directory: str) -> str:
    return directory
