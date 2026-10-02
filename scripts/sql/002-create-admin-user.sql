--
-- Licensed to the Apache Software Foundation (ASF) under one
-- or more contributor license agreements.  See the NOTICE file
-- distributed with this work for additional information
-- regarding copyright ownership.  The ASF licenses this file
-- to you under the Apache License, Version 2.0 (the
-- "License"); you may not use this file except in compliance
-- with the License.  You may obtain a copy of the License at
--
--   http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing,
-- software distributed under the License is distributed on an
-- "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
-- KIND, either express or implied.  See the License for the
-- specific language governing permissions and limitations
-- under the License.
--

-- Create default admin user without hardcoded secret.
-- Password is supplied at apply time:
--   psql -v v_admin_user="guacadmin" -v v_admin_hash="<hex sha256(password||salt)>" -v v_admin_salt="<hex>" -f 002-create-admin-user.sql
-- See scripts/bootstrap-segportal.sh for hash generation.
INSERT INTO guacamole_entity (name, type) VALUES (:'v_admin_user', 'USER');
INSERT INTO guacamole_user (entity_id, password_hash, password_salt, password_date)
SELECT
    entity_id,
    decode(:'v_admin_hash', 'hex'),
    decode(:'v_admin_salt', 'hex'),
    CURRENT_TIMESTAMP
FROM guacamole_entity WHERE name = :'v_admin_user' AND guacamole_entity.type = 'USER';

-- Grant this user all system permissions
INSERT INTO guacamole_system_permission (entity_id, permission)
SELECT entity_id, permission::guacamole_system_permission_type
FROM (
    VALUES
        (:'v_admin_user', 'CREATE_CONNECTION'),
        (:'v_admin_user', 'CREATE_CONNECTION_GROUP'),
        (:'v_admin_user', 'CREATE_SHARING_PROFILE'),
        (:'v_admin_user', 'CREATE_USER'),
        (:'v_admin_user', 'CREATE_USER_GROUP'),
        (:'v_admin_user', 'ADMINISTER')
) permissions (username, permission)
JOIN guacamole_entity ON permissions.username = guacamole_entity.name AND guacamole_entity.type = 'USER';

-- Grant admin permission to read/update/administer self
INSERT INTO guacamole_user_permission (entity_id, affected_user_id, permission)
SELECT guacamole_entity.entity_id, guacamole_user.user_id, permission::guacamole_object_permission_type
FROM (
    VALUES
        (:'v_admin_user', :'v_admin_user', 'READ'),
        (:'v_admin_user', :'v_admin_user', 'UPDATE'),
        (:'v_admin_user', :'v_admin_user', 'ADMINISTER')
) permissions (username, affected_username, permission)
JOIN guacamole_entity          ON permissions.username = guacamole_entity.name AND guacamole_entity.type = 'USER'
JOIN guacamole_entity affected ON permissions.affected_username = affected.name AND guacamole_entity.type = 'USER'
JOIN guacamole_user            ON guacamole_user.entity_id = affected.entity_id;