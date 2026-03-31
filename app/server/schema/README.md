# Database Tables and Dependencies

This document outlines the tables in the dynamic EAV IT Asset Management System schema, outlining the overarching zero-race-condition paradigm.

### `categories` & `sub_categories`
* Contains robust dynamic taxonomy fields assigning explicit names, foreign key cascading loops, and description models dynamically organizing standard groupings.

### `asset_attributes` & `asset_attribute_values`
* Handles explicit Entity-Attribute-Value (EAV) dynamic scaling parameter mappings (e.g. independently tracking RAM indices vs CPU models against base categories autonomously beyond table column limits).

### `assets`
* **asset_id** (Primary Key, String)
* **name**
* **category_id** (Foreign Key -> `categories.category_id`)
* **sub_category_id** (Foreign Key -> `sub_categories.sub_category_id`)
* **brand**
* **branch**
* **purchased_date**
* **total_quantity** (Integer)
* **asset_status** (Enum: `ACTIVE`, `ALLOCATED`, `IN_REPAIR`, `WARRANTY`, `RETIRED`, `LOST`, `DAMAGED`)
* **created_at**
* *Note*: Precise operational inventory is dynamically grouped algorithmically through direct live queries bridging the tracking index (`unused = total_quantity - COUNT(ALLOCATED)`) eliminating manual tracking integers natively prohibiting race-condition structural database corruptions identically per branch.

### `tracking`
* **tracking_id** (Primary Key, String)
* **asset_id** (Foreign Key -> `assets.asset_id`)
* **asset_name**
* **emp_id** (Foreign Key -> `employees.employee_id`)
* **from_branch**
* **to_branch**
* **movement_type** (Enum: `ALLOCATE`, `RETURN`, `TRANSFER`, `REPAIR`, `WARRANTY`, `REPLACE`, `ONBOARD`, `OFFBOARD`)
* **movement_reason** (Text)
* **allocation_type** (Enum: `TEMPORARY`, `PERMANENT`)
* **assigned_date**
* **transfer_status**

### `employees`
* Tracks global operational models mapping tightly to standard nested Role arrays (`admin`, `hr`, `manager`, `support_team`, `employee`) securely enforcing global standard bcrypt password hash variables seamlessly globally securely mapping active statuses dynamically seamlessly.

### `requests`
* Contains robust metadata pipelines executing explicit strict conditional `Employee -> Support Triage -> Branch Manager -> Admin (Out of Stock)` loop workflows dictating absolute physical and financial lifecycle authorizations securely algorithmically.
