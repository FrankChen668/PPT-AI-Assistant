#!/usr/bin/env python3
"""
Public smoke test: Workbench basic imports and key entry points
"""
import sys


def test_workbench_imports():
    """Test that key Workbench modules can be imported."""
    # Test core modules
    import workbench.server
    import workbench.generation
    import workbench.content_planning
    import workbench.page_director
    import workbench.project_writer
    import workbench.state
    import workbench.status_service
    import workbench.task_store
    import workbench.task_writer
    import workbench.connections
    import workbench.integrations
    import workbench.recommendations
    import workbench.quality_policy
    import workbench.healthcheck

    # Test key functions/classes exist
    assert hasattr(workbench.server, 'main')
    assert hasattr(workbench.generation, 'auto_generate_slide')
    assert hasattr(workbench.content_planning, 'plan_rough_deck_content')
    assert hasattr(workbench.page_director, 'direct_page')
    assert hasattr(workbench.project_writer, 'split_explicit_pages')
    assert hasattr(workbench.healthcheck, 'main')

    print("Workbench imports test PASSED")


def test_my_ppt_skill_imports():
    """Test that my-ppt-skill modules can be imported."""
    import sys
    sys.path.insert(0, 'my-ppt-skill')
    import scripts.build_project
    import scripts.qa_project
    import scripts.document_intake

    assert hasattr(scripts.build_project, 'main')
    assert hasattr(scripts.qa_project, 'main')
    assert hasattr(scripts.document_intake, 'main')

    print("my-ppt-skill imports test PASSED")


if __name__ == "__main__":
    test_workbench_imports()
    test_my_ppt_skill_imports()