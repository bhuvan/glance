# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import webob.exc

from glance.common import exception
from glance.common import wsgi
from glance.openstack.common import cfg

context_opts = [
    cfg.BoolOpt('owner_is_tenant', default=True),
    cfg.StrOpt('admin_role', default='admin'),
    cfg.BoolOpt('allow_anonymous_access', default=False),
    ]

CONF = cfg.CONF
CONF.register_opts(context_opts)


class RequestContext(object):
    """
    Stores information about the security context under which the user
    accesses the system, as well as additional request information.
    """

    def __init__(self, auth_tok=None, user=None, tenant=None, roles=None,
                 is_admin=False, read_only=False, show_deleted=False,
                 owner_is_tenant=True):
        self.auth_tok = auth_tok
        self.user = user
        self.tenant = tenant
        self.roles = roles or []
        self.is_admin = is_admin
        self.read_only = read_only
        self._show_deleted = show_deleted
        self.owner_is_tenant = owner_is_tenant

    @property
    def owner(self):
        """Return the owner to correlate with an image."""
        return self.tenant if self.owner_is_tenant else self.user

    @property
    def show_deleted(self):
        """Admins can see deleted by default"""
        if self._show_deleted or self.is_admin:
            return True
        return False


class ContextMiddleware(wsgi.Middleware):

    def __init__(self, app):
        super(ContextMiddleware, self).__init__(app)

    def process_request(self, req):
        """Convert authentication information into a request context

        Generate a RequestContext object from the available
        authentication headers and store on the 'context' attribute
        of the req object.

        :param req: wsgi request object that will be given the context object
        :raises webob.exc.HTTPUnauthorized: when value of the X-Identity-Status
                                            header is not 'Confirmed' and
                                            anonymous access is disallowed
        """
        if req.headers.get('X-Identity-Status') == 'Confirmed':
            req.context = self._get_authenticated_context(req)
        elif CONF.allow_anonymous_access:
            req.context = self._get_anonymous_context()
        else:
            raise webob.exc.HTTPUnauthorized()

    def _get_anonymous_context(self):
        kwargs = {
            'user': None,
            'tenant': None,
            'roles': [],
            'is_admin': False,
            'read_only': True,
        }
        return RequestContext(**kwargs)

    def _get_authenticated_context(self, req):
        #NOTE(bcwaldon): X-Roles is a csv string, but we need to parse
        # it into a list to be useful
        roles_header = req.headers.get('X-Roles', '')
        roles = [r.strip().lower() for r in roles_header.split(',')]

        #NOTE(bcwaldon): This header is deprecated in favor of X-Auth-Token
        deprecated_token = req.headers.get('X-Storage-Token')

        kwargs = {
            'user': req.headers.get('X-User-Id'),
            'tenant': req.headers.get('X-Tenant-Id'),
            'roles': roles,
            'is_admin': CONF.admin_role.strip().lower() in roles,
            'auth_tok': req.headers.get('X-Auth-Token', deprecated_token),
            'owner_is_tenant': CONF.owner_is_tenant,
        }

        return RequestContext(**kwargs)


class UnauthenticatedContextMiddleware(wsgi.Middleware):

    def __init__(self, app):
        super(UnauthenticatedContextMiddleware, self).__init__(app)

    def process_request(self, req):
        """Create a context without an authorized user."""
        kwargs = {
            'user': None,
            'tenant': None,
            'roles': [],
            'is_admin': True,
        }

        req.context = RequestContext(**kwargs)
