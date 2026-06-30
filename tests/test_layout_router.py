from __future__ import annotations

from pathlib import Path

from PIL import Image

from electronic_recognition.config import Settings
from electronic_recognition.layout_router import LayoutRouter
from electronic_recognition.models import ParsedDocument, ParsedPage


def test_layout_router_excludes_structured_regions_from_component_views(
    tmp_path: Path,
) -> None:
    page_path = tmp_path / "page-1.png"
    Image.new("RGB", (1000, 1000), "white").save(page_path)
    document = ParsedDocument(
        filename="drawing.png",
        pages=[
            ParsedPage(
                1,
                "",
                str(page_path),
                width=1000,
                height=1000,
            )
        ],
    )
    settings = Settings(
        layout_routing_enabled=True,
        tile_grid=2,
        region_tile_overlap=0.0,
    )
    router = LayoutRouter(settings)
    layouts = router.route(
        document,
        page_path,
        title_block={"page": 1, "region": [0, 0, 500, 500]},
        component_table={},
    )

    component_views = [
        region for region in layouts[0].regions if region.route == "component"
    ]
    assert layouts[0].regions[0].region_type == "title_block"
    assert all(
        region.bounds[0] >= 500 or region.bounds[1] >= 500
        for region in component_views
    )
    assert len(component_views) < 4
