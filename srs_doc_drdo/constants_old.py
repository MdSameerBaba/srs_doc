# constants.py — static data: file extensions, SRS sections, prompts, thinking messages

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".py": "Python", ".c": "C", ".cpp": "C++", ".h": "C/C++ Header",
    ".hpp": "C++ Header", ".java": "Java", ".cs": "C#",
    ".js": "JavaScript", ".ts": "TypeScript", ".jsx": "React JSX",
    ".tsx": "React TSX", ".vue": "Vue", ".html": "HTML", ".css": "CSS",
    ".scss": "SCSS", ".go": "Go", ".rs": "Rust", ".swift": "Swift",
    ".kt": "Kotlin", ".dart": "Dart", ".php": "PHP", ".rb": "Ruby",
    ".pl": "Perl", ".lua": "Lua", ".r": "R", ".scala": "Scala",
    ".m": "MATLAB/Obj-C", ".json": "JSON", ".xml": "XML",
    ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".ini": "INI",
    ".cfg": "Config", ".env": "Env", ".sh": "Shell", ".bash": "Bash",
    ".zsh": "Zsh", ".ps1": "PowerShell", ".md": "Markdown",
    ".txt": "Text", ".sql": "SQL", ".pdf": "PDF", ".csv": "CSV",
}

SRS_SECTIONS = {
    "1_introduction": {
        "title": "1. Introduction",
        "subsections": {
            "1_1_system_overview":  "1.1 System Overview",
            "1_2_purpose":          "1.2 Purpose",
            "1_3_scope":            "1.3 Scope",
            "1_4_users_and_sites":  "1.4 Users and Sites",
        }
    },
    "2_acronyms": {
        "title": "2. Acronyms",
        "subsections": {}
    },
    "3_reference_documents": {
        "title": "3. Reference Documents",
        "subsections": {}
    },
    "4_product_description": {
        "title": "4. Product Description",
        "subsections": {
            "4_1_system_functions":      "4.1 System Functions",
            "4_1_1_display":             "4.1.1 Display",
            "4_1_2_command_transmission":"4.1.2 Command Transmission",
            "4_1_3_fire_sequence":       "4.1.3 Fire Sequence Initiation",
            "4_1_4_data_logging":        "4.1.4 Data Logging",
            "4_2_software_objectives":   "4.2 Software Objectives",
            "4_3_databases":             "4.3 Databases used, if any",
            "4_4_os_compilers":          "4.4 Operating System, compilers used",
        }
    },
    "5_system_features": {
        "title": "5. System Features",
        "subsections": {
            "5_1_issue_commands":   "5.1 Issue Commands to IAM-U",
            "5_2_display_seeker":   "5.2 Display Seeker Image",
            "5_3_firing_sequence":  "5.3 Firing Sequence and Auto Ready Sequence",
            "5_4_data_logging":     "5.4 Data Logging and Checkout Operations",
        }
    },
    "6_states_and_modes": {
        "title": "6. States and Modes",
        "subsections": {}
    },
    "7_detailed_sw_requirement": {
        "title": "7. Detailed Software Requirement",
        "subsections": {
            "7_1_summary":              "7.1 Summary of Requirements",
            "7_1_1_ccu_module":         "7.1.1 CCU Module",
            "7_2_non_functional":       "7.2 Non-Functional Requirements",
            "7_2_1_performance":        "7.2.1 Performance Requirements",
            "7_3_software_attributes":  "7.3 Software Attributes",
            "7_3_1_reliability":        "7.3.1 Reliability",
            "7_3_2_availability":       "7.3.2 Availability",
            "7_3_3_security":           "7.3.3 Security",
            "7_3_4_maintenance":        "7.3.4 Maintenance",
            "7_3_5_portability":        "7.3.5 Portability",
            "7_3_6_testability":        "7.3.6 Testability",
        }
    },
    "8_timing_requirements": {
        "title": "8. Timing Requirements",
        "subsections": {}
    },
    "9_loadable_data": {
        "title": "9. Loadable Data Requirements",
        "subsections": {}
    },
    "10_interface_requirements": {
        "title": "10. Internal and External Interface Requirement",
        "subsections": {
            "10_1_hardware_interfaces":      "10.1 Hardware Interfaces",
            "10_2_software_interfaces":      "10.2 Software Interfaces",
            "10_3_communications_interfaces":"10.3 Communications Interfaces",
        }
    },
    "11_traceability_matrix": {
        "title": "11. Traceability Matrix",
        "subsections": {}
    },
}

_NO_CODE_RULE = (
    "- NO CODE IN OUTPUT. The SRS document must contain zero lines of source code. "
    "Do NOT include any code snippets, function signatures, class definitions, variable declarations, "
    "import statements, or fenced code blocks (no triple-backtick blocks). "
    "Describe what the system does in plain English — never show implementation code.\n"
    "- Do NOT fabricate or hallucinate information. Only write what is directly evidenced "
    "by the uploaded project files. If something cannot be determined, write: "
    "\"Not determinable from the provided codebase.\"\n"
    "- Do NOT use weasel words: \"typically\", \"usually\", \"it can be assumed\", \"likely\", \"generally\".\n"
    "- Write in formal, professional English prose. Use Markdown headings, tables, and numbered lists.\n"
)

SECTION_PROMPTS = {
    "1_introduction": f"""
Generate ONLY Section 1 — Introduction of the SRS.

STRICT RULES:
{_NO_CODE_RULE}
**1.1 System Overview**
Describe the system in plain English based only on what the uploaded files reveal. Identify the system type (web application, command-line tool, embedded system, API service, etc.) from concrete evidence in the file names, directory structure, configuration files, and documentation present. Do not reproduce any source code.

**1.2 Purpose**
State the purpose of the system as evidenced by README files, comments, configuration, or the overall structure of the project. Describe only the intended audience that is evident from the documentation or role definitions found in the project.

**1.3 Scope**
Describe what the system does, in plain English, as supported by the uploaded files. Only state what the system does NOT do if this is explicitly documented or clearly absent from the project.

**1.4 Users and Sites**
List only user roles or personas that are explicitly defined in the project (for example, through role-based access control definitions, user type constants, or documentation). List only deployment environments that are evident from configuration files or infrastructure definitions.

Format: Markdown with numbered headings. No code.
""",

    "2_acronyms": f"""
Generate ONLY Section 2 — Acronyms and Abbreviations.

STRICT RULES:
{_NO_CODE_RULE}
- List ONLY acronyms and abbreviations that actually appear in the uploaded project files (in comments, configuration files, README, or file names).
- Do NOT pad the list with generic industry acronyms not found in this project.
- If an acronym's meaning cannot be determined from the project files, mark it as: "Definition not found in project files."

Format: Markdown table with columns — Acronym | Full Form / Definition | Where Found.
Sort alphabetically. Include only what is evidenced. No code.
""",

    "3_reference_documents": f"""
Generate ONLY Section 3 — Reference Documents.

STRICT RULES:
{_NO_CODE_RULE}
- List ONLY libraries, frameworks, standards, and external services that are explicitly referenced in the project (dependency declaration files such as requirements.txt, package.json, pom.xml, go.mod; configuration files; README).
- Do NOT add IEEE/ISO standards or external documentation unless they are explicitly referenced in the project files.
- Do NOT invent version numbers or URLs not present in the project files.

Format: Markdown table — # | Name | Purpose | Version / Source (as declared in project). No code.
""",

    "4_product_description": f"""
Generate ONLY Section 4 — Product Description of the SRS.

STRICT RULES:
{_NO_CODE_RULE}
**4.1 System Functions**
Describe the main functions of the system in plain English, based only on what the uploaded project files reveal. Identify what the software performs — describe capabilities, not implementation mechanics.

**4.1.1 Display**
Describe display-related functionality found in the project: user interface components, data presentation, screen output, or visual management. Reference which project files provide evidence for this. If no display functionality is present, state so.

**4.1.2 Command Transmission**
Describe any command transmission, messaging, inter-process communication, serial or network communication, or command dispatch capabilities found in the project. Reference the specific files that provide evidence. If none are found, state so.

**4.1.3 Fire Sequence Initiation**
Describe any fire sequence, launch sequence, activation sequence, or trigger initiation capability found in the project files. Reference the specific file names that provide evidence. If none are found, write: "Not determinable from the provided codebase."

**4.1.4 Data Logging**
Describe any logging, event recording, telemetry, or data persistence capability found in the project. State what is logged, when, and where, based on evidence in the project files. Reference specific file names.

**4.2 Software Objectives**
State the software objectives as evidenced by README files, comments, configuration, or the overall structure of the project. Describe only goals that are supported by the implemented functionality found in the project files.

**4.3 Databases used, if any**
List only databases, object-relational mappers, or data stores that are explicitly referenced in the project dependency or configuration files (for example, SQLite, PostgreSQL, MongoDB, Redis). If no database usage is found, state: "No database usage found in the project files."

**4.4 Operating System, compilers used**
Identify operating system targets, compiler versions, runtime environments, or build tools that are explicitly declared in the project files (for example, in dependency files, build scripts, container definitions, or CI configuration). Do NOT guess — only report what is explicitly stated in the project files.

Format: Markdown with numbered headings. No code.
""",

    "5_system_features": f"""
Generate ONLY Section 5 — System Features of the SRS.

STRICT RULES:
{_NO_CODE_RULE}
For each system feature, provide in plain English:
  - **Description**: What the feature does as a capability.
  - **Inputs**: What data or signals the feature accepts (described in plain English).
  - **Processing**: What the feature does with its inputs (described as behaviour, not implementation).
  - **Outputs**: What results the feature produces.
  - **Source File(s)**: Which project file(s) provide evidence for this feature.

**5.1 Issue Commands to IAM-U**
Describe the command issuance capability to IAM-U (or equivalent subsystem) as evidenced by the project files. Describe the purpose and behaviour of this feature in plain English. If this capability is not found in the project, state so.

**5.2 Display Seeker Image**
Describe the seeker image display capability as evidenced by the project files. Describe what is displayed, how it is updated, and any overlay or annotation functionality — all in plain English. If this capability is not found, state so.

**5.3 Firing Sequence and Auto Ready Sequence**
Describe the firing sequence and auto-ready sequence capabilities as evidenced by the project files. Describe the sequence of events, timing, and conditions in plain English. If this capability is not found in the project, state so.

**5.4 Data Logging and Checkout Operations**
Describe the data logging and checkout or diagnostic capabilities as evidenced by the project files. Describe what is recorded, when, in what format, and what diagnostic checks are performed — all in plain English. Reference the file names that provide evidence.

Format: Markdown with numbered headings. No code.
""",

    "6_states_and_modes": f"""
Generate ONLY Section 6 — States and Modes of the SRS.

STRICT RULES:
{_NO_CODE_RULE}
- Only describe states and modes that are explicitly implemented in the project files (for example, state machine logic, mode enumeration constants, status flags, or mode-switching logic evident from file names and project structure).
- Do NOT invent states or modes that are typical for this class of system but are not present in the project.
- Describe all states, modes, and transitions in plain English — no code, no variable names, no function names.
- If no explicit state or mode management is found, write: "No explicit state or mode management found in the provided project files." Then describe any implicit mode-like behaviour that is evident from the project structure.

**6.1 System States**
List each distinct system state found in the project. For each state, describe:
  - The name of the state (in plain English)
  - The behaviour of the system in this state
  - The condition that causes the system to enter this state
  - The condition that causes the system to leave this state
  - Which project file provides evidence for this state

**6.2 System Modes**
List each operating mode found in the project. For each mode, describe:
  - The name of the mode (in plain English)
  - The behaviour of the system in this mode
  - How the mode is activated and deactivated
  - How this mode differs functionally from other modes
  - Which project file provides evidence for this mode

**6.3 State Transition Table**
If state transitions are evident in the project, provide a state-transition table:
| Current State | Event / Trigger | Next State | Action Taken |
Include only rows that are directly supported by evidence in the project files.

Format: Markdown with numbered headings and a transition table where applicable. No code.
""",

    "7_detailed_sw_requirement": f"""
Generate ONLY Section 7 — Detailed Software Requirement of the SRS.

STRICT RULES:
{_NO_CODE_RULE}
- Derive every requirement directly from capabilities evident in the uploaded project files.
- Write all requirements as formal "The system shall..." statements in plain English.
- Do NOT invent requirements not supported by evidence in the project files.

**7.1 Summary of Requirements**
Provide a numbered summary table of all software requirements identified in the project.
Format: | REQ-ID | Requirement Summary | Type (Functional / Non-Functional) | Source File |
List only requirements that are directly evidenced by the project files.

**7.1.1 CCU Module**
Describe all requirements specific to the CCU (Central Control Unit) module or equivalent central control component found in the project. For each requirement:
- State the requirement as: REQ-CCU-[NNN]: The system shall [plain English behaviour].
- Identify the source file that provides evidence.
If no CCU module is found in the project, state: "No CCU module identified in the provided project files."

**7.2 Non-Functional Requirements**
List all non-functional requirements evidenced by the project files. Write each as:
REQ-NF-[NNN]: The system shall [plain English quality attribute requirement]. Evidence: [file name].
Group by quality attribute type.

**7.2.1 Performance Requirements**
List only performance requirements that are directly evidenced by configuration, design patterns, or explicit targets in the project files.
Format: REQ-PERF-[NNN]: The system shall [plain English performance statement]. Evidence: [file name].
Do NOT invent specific response times or throughput numbers unless they appear in the project files.

**7.3 Software Attributes**
Describe the software quality attributes as evidenced by the project design, structure, and configuration.

**7.3.1 Reliability**
Describe reliability characteristics evidenced by error-handling patterns, retry logic, exception management, or fault-detection mechanisms found in the project files. State as: REQ-REL-[NNN]: [plain English reliability requirement].

**7.3.2 Availability**
Describe availability requirements or design provisions evidenced by the project files (for example, health-check endpoints, watchdog mechanisms, redundancy configuration). If not evidenced, state: "No explicit availability provisions found in the project files."

**7.3.3 Security**
Describe security requirements evidenced by authentication logic, encryption usage, access control, input validation, or security-related configuration found in the project files.
Format: REQ-SEC-[NNN]: The system shall [plain English security requirement]. Evidence: [file name].

**7.3.4 Maintenance**
Describe maintainability provisions evidenced by logging mechanisms, diagnostic interfaces, configuration management, modular design, or inline documentation found in the project files. State as: REQ-MNT-[NNN]: [plain English maintainability requirement].

**7.3.5 Portability**
Describe portability provisions evidenced by platform-independent design, abstraction layers, configuration-driven behaviour, or cross-platform build definitions found in the project files. If none are found, state: "No explicit portability provisions found in the project files."

**7.3.6 Testability**
Describe testability provisions evidenced by the presence of unit tests, test harnesses, mock interfaces, diagnostic modes, or test configuration files in the project. If none are found, state: "No explicit test infrastructure found in the project files."

Format: Markdown with numbered headings. No code.
""",

    "8_timing_requirements": f"""
Generate ONLY Section 8 — Timing Requirements of the SRS.

STRICT RULES:
{_NO_CODE_RULE}
- List ONLY timing requirements that are directly evidenced by the project files (for example, timeout values in configuration, polling intervals, scheduling parameters, deadline constraints, watchdog timer settings, or explicit timing comments in documentation).
- Do NOT fabricate timing values not present in the project files.
- If a timing constraint cannot be determined from the project, write: "Not determinable from the provided project files."

For each timing requirement found, provide:
| REQ-TIM-ID | Description | Timing Value / Constraint | Evidence (file name) |

Also describe in plain English:
- Any periodic tasks or scheduled operations and their intervals.
- Any real-time constraints or deadline requirements.
- Any inter-task or inter-process timing dependencies.
- Any hardware synchronisation timing requirements.

If no timing requirements are found in the project files, state clearly: "No explicit timing requirements found in the provided project files." and describe any implicit timing behaviour evident from the system design.

Format: Markdown with a requirements table and plain English description. No code.
""",

    "9_loadable_data": f"""
Generate ONLY Section 9 — Loadable Data Requirements of the SRS.

STRICT RULES:
{_NO_CODE_RULE}
- Describe ONLY data that is loaded into the system at runtime, initialisation, or mission-time, as evidenced by the project files (for example, configuration files, parameter tables, calibration data, look-up tables, mission data, firmware images, or database seed files).
- Do NOT invent data types or formats not evidenced in the project files.
- If no loadable data is found, state: "No loadable data requirements found in the provided project files."

For each loadable data item found, describe:
| Data Item | Description | Format / Type | Load Trigger (startup / runtime / on-demand) | Source File |

Also describe in plain English:
- How and when the data is loaded into the system.
- Any validation or integrity checks performed on the loaded data.
- Any versioning or compatibility requirements for the loadable data.
- Storage location (memory, file system, database) as evidenced by the project.

Format: Markdown with a data table and plain English description. No code.
""",

    "10_interface_requirements": f"""
Generate ONLY Section 10 — Internal and External Interface Requirements of the SRS.

STRICT RULES:
{_NO_CODE_RULE}
- Describe ONLY interfaces that are directly evidenced by the project files.
- Do NOT invent interface specifications, protocols, or signal definitions not present in the project.
- If an interface sub-section has no evidence in the project, state: "Not determinable from the provided project files."

**10.1 Hardware Interfaces**
Describe all hardware interfaces evidenced by the project files (for example, serial port configurations, GPIO definitions, CAN bus settings, USB descriptors, SPI/I2C device drivers, or hardware abstraction layer definitions).
For each hardware interface, provide:
| Interface Name | Hardware Device | Protocol / Bus | Data Rate / Parameters | Source File |
Describe the purpose and direction of each interface in plain English.

**10.2 Software Interfaces**
Describe all software interfaces evidenced by the project files (for example, APIs, shared libraries, operating system services, middleware, inter-process communication mechanisms, or software abstraction layers).
For each software interface, provide:
| Interface Name | Interfacing Component | Interface Type (API / IPC / library / OS service) | Purpose | Source File |
Describe data exchanged across each software interface in plain English.

**10.3 Communications Interfaces**
Describe all communications interfaces evidenced by the project files (for example, network sockets, communication protocols, message formats, data link layer interfaces, or wireless communication configurations).
For each communications interface, provide:
| Interface Name | Protocol | Data Rate / Bandwidth | Message Format | Source File |
Describe the purpose and direction of data flow for each communications interface in plain English.

Format: Markdown with numbered headings and interface tables. No code.
""",

    "11_traceability_matrix": f"""
Generate ONLY Section 11 — Traceability Matrix of the SRS.

STRICT RULES:
{_NO_CODE_RULE}
- Build the traceability matrix using ONLY the requirements that have been identified and documented in Sections 4 through 10 of this SRS.
- Each row must map a specific requirement ID to the project file(s) that provide evidence for it.
- Do NOT invent requirement IDs or source files not established in the earlier sections.
- If a requirement cannot be traced to a specific project file, mark the source as: "Derived from system design."

Provide the traceability matrix in the following format:

**11.1 Requirements to Source File Traceability**
| REQ-ID | Requirement Summary | Section | Source File(s) |
List ALL requirement IDs identified across Sections 7–10, one row per requirement.

**11.2 Requirements to System Feature Traceability**
| REQ-ID | Requirement Summary | System Feature / Module | Verification Method |
Map each requirement to the system feature or module it belongs to.
For Verification Method, choose from: Review | Analysis | Test | Demonstration — based on the nature of the requirement as evidenced by the project.

**11.3 Traceability Summary**
State in plain English:
- Total number of functional requirements identified.
- Total number of non-functional requirements identified.
- Number of requirements traceable to specific source files.
- Number of requirements derived from system design (no direct source file evidence).

Format: Markdown with numbered headings and tables. No code.
""",
}

THINKING_MESSAGES = [
    "Analyzing project structure and architecture...",
    "Extracting system requirements from codebase...",
    "Identifying components, modules, and dependencies...",
    "Synthesizing technical documentation...",
    "Cross-referencing files for completeness...",
    "Inferring system behavior from code patterns...",
    "Documenting functional and non-functional requirements...",
    "Building comprehensive SRS section...",
    "Reviewing code for standards compliance...",
    "Finalizing documentation with technical precision...",
]
