from __future__ import annotations

import os
import platform
import shutil
from enum import Enum
from tempfile import mkdtemp
from typing import Dict, Union
from typing import Callable, Iterable, List, Set, Tuple, Union
from zipfile import ZipFile

import cv2
import numpy as np
from PIL import Image
from sanic.log import logger

from nodes.impl.dds.texconv import dds_to_png_texconv
from nodes.impl.image_formats import (
    get_available_image_formats,
    get_opencv_formats,
    get_pil_formats,
)
from nodes.properties.inputs import TextInput, EnumInput
from nodes.properties.outputs import LargeImageOutput, TextOutput
from nodes.utils.utils import get_h_w_c, split_file_path

from .. import io_group

_Decoder = Callable[[str], Union[np.ndarray, None]]
"""
An image decoder.

Of the given image is naturally not supported, the decoder may return `None`
instead of raising an exception. E.g. when the file extension indicates an
unsupported format.
"""


def get_ext(path: str) -> str:
    return split_file_path(path)[2].lower()


def _read_cv(path: str) -> np.ndarray | None:
    if get_ext(path) not in get_opencv_formats():
        # not supported
        return None

    img = None
    try:
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    except Exception as cv_err:
        logger.warning(f"Error loading image, trying with imdecode: {cv_err}")

    if img is None:
        try:
            img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        except Exception as e:
            raise RuntimeError(
                f'Error reading image image from path "{path}". Image may be corrupt.'
            ) from e

    if img is None:  # type: ignore
        raise RuntimeError(
            f'Error reading image image from path "{path}". Image may be corrupt.'
        )

    return img


def _read_pil(path: str) -> np.ndarray | None:
    if get_ext(path) not in get_pil_formats():
        # not supported
        return None

    im = Image.open(path)
    img = np.array(im)
    _, _, c = get_h_w_c(img)
    if c == 3:
        img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    elif c == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGRA)
    return img


def _read_dds(path: str) -> np.ndarray | None:
    if get_ext(path) != ".dds":
        # not supported
        return None

    if platform.system() != "Windows":
        # texconv is only supported on Windows.
        return None

    png = dds_to_png_texconv(path)
    try:
        return _read_cv(png)
    finally:
        os.remove(png)


def _for_ext(ext: str | Iterable[str], decoder: _Decoder) -> _Decoder:
    ext_set: Set[str] = set()
    if isinstance(ext, str):
        ext_set.add(ext)
    else:
        ext_set.update(ext)

    return lambda path: decoder(path) if get_ext(path) in ext_set else None


_decoders: List[Tuple[str, _Decoder]] = [
    ("pil-jpeg", _for_ext([".jpg", ".jpeg"], _read_pil)),
    ("cv", _read_cv),
    ("texconv-dds", _read_dds),
    ("pil", _read_pil),
]

valid_formats = get_available_image_formats()


class TEXTURE(Enum):
    Albedo = "Albedo"
    SpecTeam = "SpecTeam"
    normalsTS = "normals"


TEX_LABEL: Dict[TEXTURE, str] = {
    TEXTURE.Albedo: "Albedo",
    TEXTURE.SpecTeam: "SpecTeam",
    TEXTURE.normalsTS: "normalsTS",
}


@io_group.register(
    schema_id="chainner:image:load:FAF",
    name="Load Image FAF",
    description=(
        "Load image from specified file. This node will output the loaded image, the"
        " directory of the image file, and the name of the image file (without file"
        " extension)."
    ),
    icon="BsFillImageFill",
    inputs=[
        # TextInput("Root directory", min_length = 5, default = "C:\devel\\FAF\\fa\\units\\"),
        TextInput("Root directory", min_length = 5,
                  default = "g:\\Steam\\SteamApps\\common\\Supreme Commander Forged Alliance\\gamedata\\units.scd"),
        TextInput("Unit name", default="UEB0301", min_length = 3),
        EnumInput(TEXTURE, "Texture", option_labels = TEX_LABEL, default = TEXTURE.Albedo),
        TextInput("Target directory", default="c:\\devel\\FAF\\fa\\units\\"),

    ],
    outputs=[
        LargeImageOutput().with_docs(
            "The node will display a preview of the selected image as well as type"
            " information for it. Connect this output to the input of another node to"
            " pass the image to it."
        ),
        TextOutput("Dir", output_type = "string::concat(Input0)"),
        TextOutput("Unit", output_type = "string::concat(Input1)"),
        TextOutput("Texture",
                   output_type = """
                        let sep = "\\\\";
                        let tex = match Input2 {
                            TEXTURE::Albedo => "Albedo",
                            TEXTURE::Specteam => "SpecTeam",
                            TEXTURE::Normalsts => "normalsTS",
                        };
                        string::concat(Input1, "_", tex)
                    """
                   ),
        TextOutput("Target dir", output_type = "string::concat(Input3)"),
    ],
)
def load_image_node(_path: str, unit: str, texture: TEXTURE, target: str) -> Tuple[np.ndarray, str, str, str, str]:
    """Reads an image from the specified path and return it as a numpy array"""

    texture = texture.name
    filename = unit + "_" + texture

    path = _path
    compressed = False
    if path.endswith("units.scd"):
        compressed = True
        tempdir = mkdtemp(prefix = "chaiNNerSCD-")
        # logger.warning(f"making: {tempdir}")
        with ZipFile(path, 'r') as z:
            z.extract("units/" + unit + "/" + filename + ".dds", path=tempdir)
        path = tempdir + "\\units\\" + unit + "\\" + filename + ".dds"
        # logger.warning(f"loadng: {_path}")

    else:
        path = path.removesuffix("\\") + "\\" + unit + "\\" + filename + ".dds"


    logger.debug(f"Reading image from path: {path}")

    dirname, basename, _ = split_file_path(path)

    img = None
    error = None
    for name, decoder in _decoders:
        try:
            img = decoder(path)
        except Exception as e:
            error = e
            logger.warning(f"Decoder {name} failed")

        if img is not None:
            break

    if compressed:
        logger.warning(f"rmving: {tempdir}")
        shutil.rmtree(tempdir)

    if img is None:
        if error is not None:
            raise error
        raise RuntimeError(
            f'The image "{path}" you are trying to read cannot be read by chaiNNer.'
        )

    return img, _path, unit, filename, target