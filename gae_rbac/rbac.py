# -*- coding: utf-8 -*-
"""
    RBAC webapp2 for google appengine
    ~~~~~~~~~~~~~~~~~~~
    Role-Based Access Control

    This module provides a little framework to manage permissions for anything that
    requires some level of restriction. Is especifically design to be used inside handlers in webapp2
    with Google App Engine.

    Access Rules can be grouped into roles, so that a new user can be assigned to a role
    instead of having to define all rules manually, and therefore do a lot of repeated work.
    Also, custom rules per user can be defined. Those rules are not role-dependent.

    Roles can be defined from the administration panel of your web app or directly from some inicialization code.

    IMPORTANT: By default ONLY denying rules cannot access a resource. If a resource don't have a rule, access is granted.
        You can change this behaviour using the 'rbac_policy_allow' config.
        Notice that if 'rbac_policy_allow' is True you need to define rules that deny access (Flag=False) otherwise
        you need to define rules that grant access (Flag=True)
    IMPORTANT: Rules are checked in order. If you define two rules for the same resource, topic or action
        only the first one will be checked and return the permission without checking the following rules.
        However, you can use method 'sort_rules' to set the rules in order.
    IMPORTANT: All user rules are stored in the same entity on a per user basis. It is implemented as a repeated
        property. So, only a limited amount of rules can be added. If you overcome the 1MB entity size limit you
        will get an error. However, it can store thousands of rules before achieving the 1MB limit.

    For every request to your app, where you define some access permision inside the handler,
    a GET is done to retrive from the datastore the set of rules for the loggedin user.
    Ndb is used, so gets are cached into memcache.

    The permission check can be performed with a decorator from a handler method (get, post, custom_method, etc.)
    or directly inside handler code (ej. to check access to some parts of the data or webpage).

    Rbac module needs by default only one requierement and some optional ones:
    1.- The request handlers that use Rbac need to provide a property called 'user_id' which returns the user_id
        of the logged in user or None if theres no user logged in.
        This is easy to achieve if you are using webapp2_extras.auth.

    2 (Optional).- If you want to pass to Rbac object the resource you need to define a 'resource' property
        in the request handler. If you don't pass in the resource, it will be set to the request Route uri
        name if the 'automatic_resource' config is set to True or otherwise all the rules from all the resources
        will be checked.

    3 (Optional).- If you are going to use 'automatic_resource' you must define Route name for your routes.
        See https://webapp-improved.appspot.com/guide/routing.html#building-uris
        Using route names, the resource is automatically set to the Route name for each request and only
        rules for this resource will be checked.

    RbacRules basically consist of:
    -resource: typically a web url or a Route uri name (or whatever you want). Can match partial uri-names
        using '-'. (ej. rule with resource 'user-' will match resources 'user-profile', 'user-items', etc.)
    -topic: typically a part of the page (or whatever you want). Defaults to '*' which means everything.
    -name: typically a CRUD operation (or whatever you want). Defaults to '*' which means everything.
    -flag: True to allow, False to denny access (defaults to False)

    IMPORTANT: '*' in topic and action means everything. It's incompatible to have rules for the same resource
    with topic '*' an another rule with a specific topic. same with name. This abstraction is not defined in this
    code so you must eliminate specific topics or names when setting a '*' for the same resource. This is up to you.
    Althougt remember rules are checked in order!

    Usage example:
        # First of all do the imports!
        # Typically RbacMixin will go into your BaseHandler code file. Your BaseHandler class will inherit from RbacMixin.
        # RbacRole and RbacUserRules will be used to create the roles and rules. So import them to the apropiate handler.
        # Optionally import decorators: allow, deny and check_access in your handlers code.
        # No further imports are needed.

        from gae_rbac import RbacRole, RbacUserRules  # imports when defining Roles and Rules for users
        from gae_rbac import RbacMixin # import to add rbac property to your handlers.
        from gae_rbac import allow, deny, check_access # imports when checking access to your handlers

        # Define some RbacRoles and RbacRules.
        # Obviously you don't really need to use Roles and you can just use custom rules, but
        # for convenience, here we go through the Role definition process.

        role = RbacRole.new('editor') # creating an 'editor' role for our users.
        role.new_rule('admin')  # by default denying all access to 'admin' resource (this usually is url name '/admin/')
        role.new_rule('posts', flag=True) # allowing all access to 'posts' resource (this is really by default so don't need this rule)
        role.new_rule('posts', 'editpost') # denying all actions to editpost topic
        role.new_rule('posts', 'post', 'delete') # denying delete action in post topic in posts resource
        role.put()  # save this role to the datastore

        # Then create a RbacUserRules object for every user you want to control.
        # And assign roles and custum rules to each one.

        # Create rules for user and add roles and rules from RbacRoles.
        user_rule = RbacUserRules.new(self.user_id) # create set of rules for a given user
        roles = RbacRole.get_role_async(['supervisor', 'contributor']).get_result() # get roles to assing
        user_rule.add_roles(roles) # add roles and roles rules to the user roles and rules (copying from RbacRoles)

        # We can add some custom rules.
        user_rule.add_custom_rule('profile', 'edit') # Custom rule for denying access to topic 'edit' in 'profile' resource
        user.rule.put() # save this user_rule to the datastore

        # Then you can use this user rules in 2 ways:
        # (having your handlers inherit from RbacMixin assumed)
        # 1) Decorating handlers with @rbac.allow('list_of_roles', 'list of methods') or
            @rbac.deny('list_of_roles', 'list of methods') or @rbac.check_access(topic, name):

        class ProfileHandler(BaseHandler):
            @rbac.deny(['contributor', 'supervisor'])  # if user is one of this roles will get a abort(403) (Forbidden)
            def get(self):
                self.response.write('access granted to profile')

            # in the following example, notice that if there is a rule such as (topic ='update_profile', name='delete', flag=False)
            # (and suppose this is the only rule for this resource) rbac.check_access will return ALLOW access.
            @rbac.check_access('update_profile') # if rule (topic ='update_profile', name='*', flag=False) DENY, else ALLOW
            def post(self):
                self.response.write('access granted to update profile')

        # 2) Checking access inside handlers methods:
        class ProfileHandler(BaseHandler):
            def edit_profile(self):
                if self.rbac.has_access('edit_profile'):  # returns True if current user have access to this topic.
                # or
                if self.rbac.belongs_to('supervisor'): # returns True if current user has the supervisor Role.

    IMPORTANT: Checking against roles (membership) is much faster than checking rules (lookup).

    Based on concept from `tipfy ACL` (https://github.com/moraes/tipfy/blob/master/tipfy/appengine/acl.py)
    Also some Rbac concepts inspired by Flask Rbac (https://github.com/shonenada/flask-rbac/tree/master/flask_rbac)
    :copyright: 2015 by janscas.
    :license: see LICENSE.txt for more details.
"""

import hashlib
import webapp2
from google.appengine.ext import ndb
from google.appengine.api import memcache


CUSTOM_RULE_NAME = '_custom'


# This default config can be overwrited in webapp2 config dictionary with the Config_key = 'gae_rbac.rbac':
# -rbac_policy_allow: Can be True or False
# True to allow access by default. If a rule is not found, access is allowed. You must define deny rules.
# False to deny access by default. If a rule is not found, access is denied. You must define allow rules.
# -automatic_resource: True to get the resource from the Route uri name. By default True.

default_config = {'rbac_policy_allow': True,
                  'automatic_resource': True}


def tasklet(func):
    """Tasklet decorator that lets the caller specify either async or sync
    behavior at runtime.

    If sync is False (the default), the tasklet returns a future and
    can be used in asynchronous control flow from within other tasklets
    (like ndb.tasklet). If sync is True, the tasklet will wait for its
    results and return them, allowing you to call the tasklet from synchronous
    code (like ndb.synctasklet).
    """
    @ndb.utils.wrapping(func)
    def tasklet_wrapper(*args, **kwds):
        arg_name = "sync"
        sync_by_default = False
        make_sync = kwds.get(arg_name, sync_by_default)
        if make_sync:
            taskletfunc = ndb.synctasklet(func)
        else:
            taskletfunc = ndb.tasklet(func)
        if arg_name in kwds:
            del kwds[arg_name]
        return taskletfunc(*args, **kwds)
    return tasklet_wrapper


class FakeFuture(object):

    def __init__(self, future, memcache_key, delete=False):
        self.future = future
        self._memcache_key = memcache_key
        self.delete = delete

    def get_result(self):
        if isinstance(self.future, ndb.Future):
            self.future = self.future.get_result()
            if self.delete is False:
                memcache.set(self._memcache_key, self.future)
        return self.future


class RbacRule(ndb.Model):
    """Representation of a Rule

    It's allways used as a LocalStructuredProperty so no model.put() operations are done.
    """

    # holds the roles that owns this rule. Also holds CUSTOM_RULE_NAME for custom rules.
    roles = ndb.StringProperty('ro', repeated=True, indexed=False)
    # resource this rule applies for. Usually a url name (ej. 'posts') or a url (ej. '/posts/')
    resource = ndb.StringProperty('r', required=True, indexed=False)
    # the topic of the rule. May apply to a part of a page (ej. 'edit_post')
    topic = ndb.StringProperty('t', default='*', indexed=False)
    # action to perform. Maybe whatever you want but usually a CRUD operation.
    name = ndb.StringProperty('a', default='*', indexed=False)
    # permission allowed or not. Defaults to False
    flag = ndb.BooleanProperty('f', default=False, indexed=False)

    @classmethod
    def new(cls, roles, resource, topic='*', name='*', flag=False):
        """Factory method to create new Rules."""
        if roles is None:
            roles = []
        rule = cls(roles=roles, resource=resource, topic=topic, name=name, flag=flag)
        return rule

    @staticmethod
    def get_signature(resource, topic, name, flag):
        """Represents the signature of a rule. For deduplication purposes."""
        return "%s:%s:%s:%s" % (resource, topic, name, flag)

    @property
    def signature(self):
        """Returns the signature of this rule."""
        return self.get_signature(self.resource, self.topic, self.name, self.flag)

    def add_role(self, role_name):
        """Adds the role name to the role avoiding duplicates.
        :returns:
            the rule roles list.
        """
        if role_name not in self.roles:
            self.roles.append(role_name)
        return self.roles

    def __eq__(self, other):
        return self.signature == other.signature

    def __ne__(self, other):
        return not self == other

    def __lt__(self, other):
        if self.resource == '*' and other.resource != '*':
            return False
        if self.resource[-1] == '-' and other.resource != '*' and other.resource[-1] != '-':
            return False
        if other.resource != '*' and other.resource[-1] != '-':
            # self.resource is a word != than '*' or != than finished with '-'
            return self.resource < other.resource
        if self.resource == other.resource:
            if self.topic == '*' and other.topic != '*':
                return False
            if other.topic != '*':
                return self.topic < other.topic
            if self.topic == other.topic:
                if self.name == '*' and other.name != '*':
                    return False
                if other.name != '*':
                    return self.name < other.name
        return True


class RbacRole(ndb.Model):
    """Representation of a Role"""

    # name of the role (ej. 'admin')
    name = ndb.StringProperty('n', required=True, indexed=True)  # indexed so it can be queried.
    # holds the rules: see https://cloud.google.com/appengine/docs/python/ndb/properties#structured
    rules = ndb.LocalStructuredProperty(RbacRule, 'ru', repeated=True)  # Not indexed by default.

    _memcache_key = 'gae-rbac_roles_list'

    @staticmethod
    def build_id(role_name):
        """Builds the id of this object to store it in the datastore"""
        role_id = hashlib.md5(role_name.lower()).hexdigest()
        return "role:%s" % role_id

    @classmethod
    def get_keys(cls, role_name=None, role_id=None):
        """Construct the Key objects"""
        assert role_name or role_id, "Provide just one: role_name or role_id"
        if role_name:
            if isinstance(role_name, basestring):
                return ndb.Key(cls, cls.build_id(role_name))
            else:
                return [ndb.Key(cls, cls.build_id(role)) for role in role_name]
        elif role_id:
            if isinstance(role_id, basestring):
                return ndb.Key(cls, role_id)
            else:
                return [ndb.Key(cls, role) for role in role_id]

    @classmethod
    @tasklet
    def get_role_async(cls, role_name_s):
        """Gets the role object from the datastore.
        It's defined as a tasklet so more operations can be done while getting the result.
        :param role_name_s:
            the role name to be retrieved OR a list of role names
        :returns:
            A RbacRole object or list of objects
        """
        if isinstance(role_name_s, basestring):
            # retrieve a single role
            role_s = yield cls.get_by_id_async(cls.build_id(role_name_s))
        else:
            # retrieve a list of roles
            roles_keys = [ndb.Key(cls, cls.build_id(role_name)) for role_name in role_name_s]
            role_s = yield ndb.get_multi_async(roles_keys)
        raise ndb.Return(role_s)

    @classmethod
    def get_all_async(cls, sync=False):
        """Gets all the role objects from the datastore. Uses memcache to cache results.
        It's defined as async so more operations can be done while getting the result.
        :param sync:
            if True returns a FakeFuture with a posible future object
        :returns:
            A list of RbacRole objects
        """
        roles = memcache.get(cls._memcache_key)
        if roles is None:
            if sync is True:
                roles = cls.query().fetch()
            else:
                roles = cls.query().fetch_async()
                roles = FakeFuture(roles, cls._memcache_key)
        else:
            if sync is False:
                roles = FakeFuture(roles, cls._memcache_key)
        return roles

    @classmethod
    def delete_role_async(cls, role_name=None, role_id=None, sync=False):
        """Deletes the role name or a list of roles
        Deleting a role does not change User Rules and Roles.
        It's defined as async so more operations can be done while getting the result.
        Just provide role_name or role_id but not both.
        :param role_name:
            a role name string or a list of roles strings.
        :param role_id:
            a role id or a list of roles ids
        :returns:
            True if succeed else False.
        """
        assert role_name or role_id, "Provide just one: role_name or role_id"
        keys = cls.get_keys(role_name, role_id)
        memcache.delete(cls._memcache_key)
        role = role_name or role_id
        if isinstance(role, basestring):
            if sync is True:
                future = keys.delete()
            else:
                future = keys.delete_async()
                future = FakeFuture(future, cls._memcache_key, delete=True)
        else:
            if sync is True:
                future = ndb.delete_multi(keys)
            else:
                future = ndb.delete_multi_async(keys)
                future = FakeFuture(future, cls._memcache_key, delete=True)
        return future

    @classmethod
    def new(cls, name, rules=None):
        """Creates a new RbacRole with optional RbacRules. Don't perform a put to the datastore.

        :param name:
            the name of the role.
        :param rules:
            a list of RbacRules to be applied to this role.
        :returns:
            a unsaved RbacRole entity.
        """
        if rules is None:
            rules = []
        role = cls(name=name, rules=rules, id=cls.build_id(name))
        memcache.delete(cls._memcache_key)
        return role

    def new_rule(self, resource, topic='*', name='*', flag=False):
        """Method to create new rules to the current role. RbacRules are never put into the datastore.
        Will add this new rule to the instance rules list.

        :returns:
            The new RbacRule object if created. None if it's allready in self.rules
        """
        signature = RbacRule.get_signature(resource, topic, name, flag)
        if signature not in self.rules_signatures:
            rule = RbacRule.new([self.name], resource, topic, name, flag)
            self.rules.append(rule)
            return rule
        return None

    def remove_rule(self, resource, topic, name, flag):
        """Method to remove a rule from the current role. RbacRules are never put into the datastore.
        Will remove this rule from the instance rules list.

        :returns:
            True if the item is removed, False otherwise
        """
        rule = RbacRule.new([self.name], resource, topic, name, flag)
        try:
            self.rules.remove(rule)
            return True
        except:
            return False

    @property
    def rules_signatures(self):
        """Returns a list of rules signatures"""
        return [r.signature for r in self.rules]

    def __eq__(self, other):
        if self.name == other.name:
            return True
        else:
            return False


class RbacUserRules(ndb.Model):
    """Object that holds the user roles and rules.
    Note that a change in a RbacRole rules will not update the RbacUserRules.
    Rules are copied to avoid datastore RPCs.
    """

    # user id rules applies for.
    user = ndb.StringProperty('u', required=True, indexed=False)
    # list of role names
    roles = ndb.StringProperty('ro', repeated=True, indexed=True)  # You can query by roles to update role definitions or delete roles
    # list of rules
    rules = ndb.LocalStructuredProperty(RbacRule, 'ru', repeated=True)  # Not indexed by default.
    # Modification date
    updated = ndb.DateTimeProperty('ud', auto_now=True, indexed=False)

    @staticmethod
    def build_id(user):
        """Returns the id name of this object to be saved to the datastore.
        :param user:
            User id
        :returns:
            The key name.
        """
        return 'rbac:%s' % str(user)

    @classmethod
    @tasklet
    def get_all_by_role(cls, role_name):
        """Gets all the RbacUserRules with the provided role_name assingned.
        :param role_name:
            the role name to query
        """
        if role_name:
            rbac_user_rules = yield cls.query(cls.roles == role_name).fetch_async()
            raise ndb.Return(rbac_user_rules)
        raise ndb.Return(None)

    @classmethod
    @tasklet
    def delete_user_rules(cls, user):
        """Deletes a RbacUserRule for a given user or list of users.
        :param user:
            the user id in string format or a list of user id's
        """
        if isinstance(user, basestring):
            future = ndb.Key(cls, cls.build_id(user)).delete_async()
        else:
            future = ndb.delete_multi_async([ndb.Key(cls, cls.build_id(u)) for u in user])
        raise ndb.Return(future)

    @classmethod
    @tasklet
    def get_rules_async(cls, user):
        """Gets the RbacUserRules from the datastore for the current user.
        It's defined as a tasklet so more operations can be done while getting the result.

        :param user:
            the user id
        :returns:
            the entity RbacUserRules for this given user
        """
        user_rules = yield cls.get_by_id_async(cls.build_id(user))
        raise ndb.Return(user_rules)

    @classmethod
    @tasklet
    def get_rules_for_resource_async(cls, user, resource=None):
        """Gets the RbacUserRules from the datastore for the current user and resource
        Getting for a resource is so common that we define this helper method.
        :param user:
            the user id
        :param resource:
            the resource to get the rules from
        :returns:
            (user_rules, roles, rules) triple or None
        """
        user_rules = yield cls.get_rules_async(user)
        if user_rules:
            rules = cls.rules_for_resource(resource, user_rules.rules)
            raise ndb.Return(user_rules, user_rules.roles, rules)
        raise ndb.Return(None)

    @classmethod
    def rules_for_resource(cls, resource, rules):
        if resource and resource != '*':
            r_rules = [rule for rule in rules if cls._is_rule_for_resource(rule.resource, resource)]
        else:
            r_rules = rules
        return r_rules

    @classmethod
    def _is_rule_for_resource(cls, rule_resource, resource):
        if rule_resource[-1] == '-':
            return rule_resource == resource[:len(rule_resource)]
        else:
            return rule_resource == resource

    @classmethod
    def new(cls, user, roles=None, rules=None):
        """Creates a new RbacUserRules for the given user"""
        if roles is None:
            roles = []
        if rules is None:
            rules = []
        user_rules = cls(user=str(user), roles=roles, rules=rules, id=cls.build_id(user))
        return user_rules

    @property
    def rules_signatures(self):
        """Returns a list of rules signatures."""
        return [r.signature for r in self.rules]

    def rules_to_dict(self):
        """Method to generate de rules dict."""
        return dict(zip(self.rules_signatures, self.rules))

    def sort_rules(self):
        """sort the rules based on the __lt__ function in RbacRules"""
        self.rules = sorted(self.rules, reverse=True)

    def add_role(self, role, sort_rules=False, use_rbac_role=True):
        """Adds the role and role rules to the user roles and rules lists.
        If the role is already added we don't do anything.
        This method don't check if a Role rules definition has changed.

        :param role:
            RbacRole Model or role name string to append to the user rules.
        :param sort_rules:
            will sort all the rules at the end. Defaults to False.
        :param use_rbac_role:
            True if you plan tu use RbacRoles. Will try to get the RbacRole if you pass role as a string
        :returns:
            (roles, rules) tuple if succeed, else None
        """
        if not isinstance(role, RbacRole):
            if isinstance(role, basestring):
                # If the role is already applied to this user don't do anything...
                if role in self.roles:
                    return None
                if not use_rbac_role:
                    self.roles.append(role)
                    return self.roles, self.rules
                role_obj = RbacRole.get_role_async(role, sync=True)
                if not role_obj:
                    # This role was not found. Return None
                    return None
                role = role_obj
            else:
                raise Exception('role must be an instance of RbacRole or a role string')

        # If the role is already applied to this user don't do anything...
        if role.name in self.roles:
            return None

        self.roles.append(role.name)

        # Call dict rules with signatures as keys.
        rules_dict = self.rules_to_dict()

        # Extend user rules with new role rules.
        # If the same rule is found, append new role to rules roles... but we don't check if rules have changed.
        for role_rule in role.rules:
            rule = rules_dict.get(role_rule.signature)
            if rule is None:
                # add the role_rule
                rules_dict[role_rule.signature] = role_rule
            else:
                # the rule has been found and may belong to other role. Append role to rule.
                rule.add_role(role.name)

        # rules_dict holds the final rules. Now we regenerate a rules list and assign it to self.rules
        self.rules = [v for k, v in rules_dict.iteritems()]
        if sort_rules:
            self.sort_rules()
        return self.roles, self.rules

    def add_roles(self, roles, sort_rules=False, use_rbac_role=True):
        """Helper method to add list of roles
        :param roles:
            a list of RbacRoles or list of role strings
        :param sort_rules:
            will sort all the rules at the end. Defaults to False.
        :param use_rbac_role:
            True if you plan tu use RbacRoles. Will try to get the RbacRole if you pass role as a string
        :returns:
            tuple (self.roles, self.rules)
        """
        for role in roles:
            self.add_role(role, use_rbac_role=use_rbac_role)
        if sort_rules:
            self.sort_rules()
        return self.roles, self.rules

    def remove_role(self, role):
        """Removes the role and role rules from the user roles and rules lists.
        :param role:
            RbacRole Model or role name string to append to the user rules.
        :returns:
            True if succeed, else None
        """
        if isinstance(role, basestring):
            role_name = role
        else:
            if isinstance(role, RbacRole):
                role_name = role.name
            else:
                raise Exception('role must be an instance of RbacRole or a role name string')

        # If the role is not present we don't do anything
        if role_name not in self.roles:
            return None
        # Remove the role name from the roles list
        self.roles.remove(role_name)

        # check every rule to look for rules from role to be removed
        new_rules = []
        for rule in self.rules:
            if role_name in rule.roles:
                if len(rule.roles) > 1:
                    # if this rule belongs to more than one role, only remove the role from the rules roles list
                    rule.roles.remove(role_name)
                    new_rules.append(rule)
            else:
                # add this rule to the final list
                new_rules.append(rule)
        self.rules = new_rules
        return True

    def update_role(self, role):
        """Updates the role rules to the RbacUserRules"""

        if isinstance(role, basestring):
            role = ndb.Key(RbacRole, RbacRole.build_id(role)).get()
        if not role:
            return False
        result = self.remove_role(role)
        if result:
            self.add_role(role)
            return True
        return False

    def add_custom_rule(self, resource, topic='*', name='*', flag=False, sort_rules=False):
        """Adds a custom rule to the current RbacUserRules
        :param sort_rules:
            will sort all the rules at the end. Defaults to False.
        :returns:
            the RbacRule object.
        """
        if not resource:
            # Because this is a custom rule, we put the CUSTOM_RULE_NAME inside the roles list.
            raise Exception('a resource name must be provided')
        # custom rule will be ignored if there is another rule with the same signature (even if is a role rule).
        rule = RbacRule.new([CUSTOM_RULE_NAME], resource, topic, name, flag)
        if rule.signature not in self.rules_signatures:
            self.rules.append(rule)
        if sort_rules:
            self.sort_rules()
        return rule

    def remove_custom_rule(self, resource=None, topic='*', name='*', flag=False, signature=None):
        """Removes a custom rule from the user rules.
        :param resource, topic, name and Flag:
            the 4 rule attributes
        :param signature:
            instead of the 4 rule attributes you can provide a rule signature
        :returns:
            True if succeed
        """
        if signature is None:
            if resource is None:
                raise Exception('you must provide at least a resource or a signature')
            signature = RbacRule.get_signature(resource, topic, name, flag)
        new_rules = []
        for rule in self.rules:
            if CUSTOM_RULE_NAME in rule.roles and rule.signature == signature:
                if len(rule.roles) > 1:
                    # if this rule belongs to more than one role,
                    # only remove the CUSTOM_RULE_NAME from the rules roles list
                    rule.roles.remove(CUSTOM_RULE_NAME)
                    new_rules.append(rule)
            else:
                # add this rule to the final list
                new_rules.append(rule)
        self.rules = new_rules
        return True

    def has_rule(self, resource, topic='*', name='*', flag=False):
        """Checks if the user have this rule.
        :param resource:
            the resource
        :param topic:
            the topic
        :param name:
            the name
        :param flag:
            the flag
        :returns:
            True if the user have this rule, False otherwise
        """
        new_rule = RbacRule.new([], resource, topic, name, flag)
        for rule in self.rules:
            if new_rule == rule:
                return True
        return False


class Rbac(object):
    """Loads rules and roles for a given user on a given resource and provides a centralized
    interface to check permissions. Each Rbac object checks the permissions	for a single user.
    """
    # Configuration key.
    config_key = __name__

    def __init__(self, user, request=None, resource=None):
        """Loads rbac config, rules and roles for a given user.
        If resource passed as None, will try to get ir from the matched Route name
        :param user:
            a user_id string to load the roles and rules for
        :param request:
            A :class:`webapp2.Request` instance.
        :param resource:
            a resource string or None.
        """
        # TODO: maybe save the request object into a instance variable?

        # load default configs and overwrite with user default configs if set.
        self.config = request.app.config.load_config(self.config_key, default_values=default_config)

        if not resource and self.config['automatic_resource'] and request:
            # If the user don't provide the resource, automatically retrieves the uri name
            # from the Route matched from the request.
            # Uri names definition on Routes are really needed for this to work.
            # if you want to avoid this automatic resource match just pass
            # a resource you want to match (non empty string) or set 'automatic_resource' to False
            resource = request.route.name or None

        # init instance variables
        self.resource = resource
        self.roles = []
        self.rules = []
        self.user = None
        self.rbac_rules = None
        self.unset = True
        # self.unset will be true if user is not provided correcty.
        # this will avoid any computation and allways return None (None means no access allowed) when asked for access.
        if user:
            self.unset = False
            self.user = str(user)
            # load roles and rules
            roles_rules = RbacUserRules.get_rules_for_resource_async(self.user, resource, sync=True)
            if roles_rules:
                self.rbac_rules, self.roles, self.rules = roles_rules

    def belongs_to(self, role_s):
        """Check to see if a user belongs to a role/s group
        :param role_s:
            role name (string) or list of role names (strings)
        :returns:
            True if the user is in this role group, False if not. None if user was not set.
        """
        if self.unset:
            return None
        if isinstance(role_s, basestring):
            return role_s in self.roles
        else:
            return any(role in self.roles for role in role_s)

    def belongs_to_all(self, roles):
        """Check to see if a user belongs to all of the roles listed
        :param roles:
            a list of roles the user maybe belongs to
        :returns:
            True if the user is in all the roles listed, False if not. None if user was not set.
        """
        if self.unset:
            return None
        return all(role in self.roles for role in roles)

    def rules_for_resource(self, resource):
        """Filters all user rules and returns a list of rules for the given resource
        :param resource:
            a resource
        :returns:
            A list of rules for the given resource
        """
        rules = []
        if self.rbac_rules:
            rules = self.rbac_rules.rules_for_resource(resource, self.rbac_rules.rules)
        return rules

    def has_access(self, topic='*', name='*', resource=None):
        """Checks if the user has access to a topic/name combination.
        If resource is provided then will look only for this resource from
        all the user rules but normally self.rules is already limited to
        the resource provided by the user or by the automatic resource
        identification if is enabled.
        :param topic:
            the topic
        :param name:
            the name
        :returns:
            True if the user has access to this rule, False if no. None if user was not set.
        """
        if self.unset:
            return None
        if resource and resource != self.resource:
            # if a resource is provided filter from all user rules
            rules = self.rules_for_resource(resource)
        else:
            rules = self.rules
        for rule in rules:
            if (rule.topic == topic or rule.topic == '*') and \
                    (rule.name == name or rule.name == '*'):
                # Topic and name matched, so return the flag
                return rule.flag
        # No match. Access is granted depending on rbac_policy_allow.
        return self.config['rbac_policy_allow']

    def update_user_rules(self, users_ids, roles_to_update):
        """Updates all RbacUserRules with a RbacRole rules.
        :param users_ids:
            a list of user ids to apply the RbacRole rules.
        :params roles_to_update:
            a list of roles to apply the rules for.
        """
        # create keys with ndb.Key(RbacUserRules, RbacUserRules.build_id(user_id))
        users_ids = users_ids or None
        roles_to_update = roles_to_update or None
        assert users_ids is not None and roles_to_update is not None
        rbac_objs = ndb.get_multi_async([ndb.Key(RbacUserRules, RbacUserRules.build_id(user_id)) for user_id in users_ids])
        rbac_roles = ndb.get_multi_async([ndb.Key(RbacRole, RbacRole.build_id(role)) for role in roles_to_update])
        rbac_objs = rbac_objs.get_result()
        if not rbac_objs:
            return False
        rbac_roles = rbac_roles.get_result()
        if not rbac_roles:
            return False
        for rbac_obj in rbac_objs:
            for rbac_role in rbac_roles:
                rbac_obj.update_role(rbac_role)
        ndb.put_multi(rbac_objs)
        return True


class RbacMixin(object):
    """A mixin that adds rbac property to a 'webapp2.RequestHandler'.
    It is work of the handler to provide the user_id property of the logged in user
    and the optional resource property.
    """

    @webapp2.cached_property
    def rbac(self):
        """Loads and returns a Rbac instance for the current request object.
        Needs the property self.user_id defined in the Handler used in conjunction with this mixin.
        Optionally you can customize the resource by defining a property 'resource' in your handler
        and assing a string value to it. Otherwise resource is get from the request Route name.
        """
        try:
            user = self.user_id
        except:
            raise Exception('self.user_id property must be implemented in the handler')
        try:
            resource = self.resource
        except:
            resource = None
        return get_rbac(user, resource, request=self.request)


class RbacUserMixin(object):
    """A mixin that adds rbac property to a user class (webapp2_extras.appengine.auth.models.User)
    Adds functionality to a user class so it can retrieve it's RbacUserRules and do more.
    """

    @webapp2.cached_property
    def rbac(self):
        """Property that returns a Rbac object given the user_id from the User Model.
        Method get_id() is implemented by default in: webapp2_extras.appengine.auth.models.User
        """
        return Rbac(self.get_id())


def allow(roles, methods=None):
    """This is a decorator function.
    RbacMixin must be implemented in the class of the handler.
    You can allow roles to access the handler method.
    self.user_id is checked allways. If None, redirect to login page.
    An example::
        @rbac.allow(['administrator', 'editor'])
        def get(self):
            return self.response.write('Access Granted!')
    :param roles:
        List of roles names.
    :param methods:
        an optional request method list to check (GET, POST, etc..)
    :returns:
        if user is denied access or no roles are passed then self.abort(403) is called
    """

    if not isinstance(roles, list):
        raise Exception('roles must be a list of string roles')

    def check_arg(handler):
        def check_allow(self, *args, **kwargs):
            if self.user_id is None:
                return self.redirect_to('login', _abort=True)
            if self.rbac.belongs_to(roles) and check_method(methods, self):
                # access allowed
                return handler(self, *args, **kwargs)
            return self.abort(403)
        return check_allow
    return check_arg


def deny(roles, methods=None):
    """This is a decorator function.
    RbacMixin must be implemented in the class of the handler.
    You can deny roles to access the handler method.
    self.user_id is checked allways. If None, redirect to login page.
    An example::
        @rbac.deny(['administrator', 'editor'])
        def get(self):
            return self.response.write('Access Granted!')
    :param roles:
        List of roles names.
    :param methods:
        an optional request method list to check (GET, POST, etc..)
    :returns:
        if user is denied access then self.abort(403) is called
    """

    if not isinstance(roles, list):
        raise Exception('roles must be a list of string roles')

    def check_arg(handler):
        def check_deny(self, *args, **kwargs):
            if self.user_id is None:
                return self.redirect_to('login', _abort=True)
            if self.rbac.belongs_to(roles) and check_method(methods, self):
                # access denied
                return self.abort(403)
            return handler(self, *args, **kwargs)
        return check_deny
    return check_arg


def check_access(topic='*', name='*', resource=None, methods=None):
    """This is a decorator function.
    RbacMixin must be implemented in the class of the handler.
    You can check access rules to allow access to the handler method.
    self.user_id is checked allways. If None, redirect to login page.
    An example::
        @rbac.check_access
        def get(self):
            return self.response.write('Access Granted!')
    :param topic:
        a topic to check
    :param name:
        a name to check
    :param resource:
        a resource to check.
    :param methods:
        an optional request method list to check (GET, POST, etc..)
    :returns:
        if user is denied access then self.abort(403) is called
    """

    def check_arg(handler):
        def check_int(self, *args, **kwargs):
            if self.user_id is None:
                return self.redirect_to('login', _abort=True)
            if self.rbac.has_access(topic, name, resource) and check_method(methods, self):
                return handler(self, *args, **kwargs)
            # access denied
            return self.abort(403)
        return check_int
    return check_arg


def check_method(methods, request_handler):
    """A helper function to check if the request is donde with the provided methods.
    :param methods:
        a list of methods (strings) (GET, POST, etc..)
    :param request_handler:
        the request object.
    :returns:
        True if request method match any in the method list (or methods is None), False otherwise.
    """
    if methods is None:
        return True
    return request_handler.request.method in methods

#: Key used to store :class:`Auth` in the request registry.
_rbac_registry_key = 'Rbac_for_webapp2'


def get_rbac(user, resource=None, key=_rbac_registry_key, request=None):
    """Returns an instance of :class:`Rbac` from the request registry.

    It'll try to get it from the current request registry, and if it is not
    registered it'll be instantiated and registered. A second call to this
    function will return the same instance.
    :param user:
        A user_id string
    :param resource:
        The resource you want the Rbac Rules to be checked against. If None, Rbac will
        try to get the resource from the request Route name
    :param key:
        The key used to store the instance in the registry. A default is used
        if it is not set.
    :param request:
        A :class:`webapp2.Request` instance used to store the instance. The
        active request is used if it is not set.
    :returns:
        A rbac instance
    """
    request = request or webapp2.get_request()
    rbac = request.registry.get(key)
    if not rbac:
        rbac = request.registry[key] = Rbac(user, request, resource)
    return rbac