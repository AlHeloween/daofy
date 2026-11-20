<!-- @title: Coding Rules Navigation -->
<!-- @purpose: Quickly locate the rule files needed at each coding stage. On first read or after completing a full workflow, call get_coding_rules(section=...) as needed for details. -->

## Coding Rules Navigation
> Last updated: 2026-07-17 | Version: 1.14.0

Choose an entry point by workflow:

## Basic Coding
```
Plan → get_coding_rules(section="planning")    # P0 pre-planning and review (required for new features)
Workflow → get_coding_rules(section="workflow")     # Workflow overview
Check API → get_coding_rules(section="kb_search")   # Search definitions
Code → get_coding_rules(section="writing")      # Code conventions
Modify files → get_coding_rules(section="delphi_file_write_rule")  # Write rules/dirty flags
Compile → get_coding_rules(section="compile")      # Compile + run_verify
Review → get_coding_rules(section="review")       # Review checklist
Cleanup → get_coding_rules(section="cleanup")      # Final cleanup + experience saving
```

## Exception Diagnosis
```
Getting started → get_coding_rules(section="human_collab")   # Trigger conditions + pre-flight self-check
Debugging → get_coding_rules(section="debugging")      # Full collection of 8.1–8.14 (six-step method / crash classification / DCC decoding / …)
```

## Automated Testing
```
Methodology (AI framework) → get_coding_rules(section="automation")
Layout audit → get_coding_rules(section="ui_layout")  # DFM static layout specification + delphi_project(action="layout")
Tool reference → read_mcp_resource("delphi://automation/script-schema")
```

## Other
```
Multi-change ordering → get_coding_rules(section="multi_change")
Experience saving → get_coding_rules(section="experience")
Knowledge base → get_coding_rules(section="kb_build")
Agent conventions → get_coding_rules(section="agent_rules")
```

`delphi://coding-rules` is the navigation entry point; read the full rule text on demand via `get_coding_rules(section=...)`.

