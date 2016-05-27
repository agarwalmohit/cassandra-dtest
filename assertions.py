from nose.tools import assert_regexp_matches, assert_equal

from cassandra import (InvalidRequest, ReadFailure,
                       ReadTimeout, Unauthorized, Unavailable, WriteFailure,
                       WriteTimeout)
from cassandra.query import SimpleStatement

from tools import rows_to_list

"""
The assertion methods in this file are used to structure, execute, and test different queries and scenarios. Use these anytime you are trying
to check the content of a table, the row count of a table, if a query should raise an exception, etc. These methods handle error messaging
well, and will help discovering and treating bugs.

An example:
Imagine some table, test:

    id | name
    1  | John Doe
    2  | Jane Doe

We could assert the row count is 2 by using:
    assert_row_count(session, 'test', 2)

After inserting [3, 'Alex Smith'], we can ensure the table is correct by:
    assert_all(session, "SELECT * FROM test", [[1, 'John Doe'], [2, 'Jane Doe'], [3, 'Alex Smith']])
or we could check the insert was successful:
    assert_one(session, "SELECT * FROM test WHERE id = 3", [3, 'Alex Smith'])

We could remove all rows in test, and assert this was sucessful with:
    assert_none(session, "SELECT * FROM test")

Perhaps we want to assert invalid queries will throw an exception:
    assert_invalid(session, "SELECT FROM test")
or, maybe after shutting down all the nodes, we want to assert an Unavailable exception is raised:
    assert_unavailable(session.execute, "SELECT * FROM test")
    OR
    assert_exception(session, "SELECT * FROM test", expected=Unavailable)

"""

def _assert_exception(fun, *args, **kwargs):
    matching = kwargs.pop('matching', None)
    expected = kwargs['expected']
    try:
        if len(args) == 0:
            fun(None)
        else:
            fun(*args)
    except expected as e:
        if matching is not None:
            assert_regexp_matches(str(e), matching)
    except Exception as e:
        raise e
    else:
        assert False, "Expecting query to raise an exception, but nothing was raised."


def assert_exception(session, query, matching=None, expected=None):
    if expected is None:
        assert False, "Expected exception should not be None. Your test code is wrong, please set `expected`."

    _assert_exception(session.execute, query, matching=matching, expected=expected)


def assert_unavailable(fun, *args):
    """
    Attempt to execute a function, and assert Unavailable, WriteTimeout, WriteFailure, ReadTimeout, or ReadFailure exception is raised.
    @param fun Function to be executed
    @param *args Arguments to be passed to the function

    Examples:
    assert_unavailable(session2.execute, "SELECT * FROM ttl_table;")
    assert_unavailable(lambda c: debug(c.execute(statement)), session)
    """
    _assert_exception(fun, *args, expected=(Unavailable, WriteTimeout, WriteFailure, ReadTimeout, ReadFailure))


def assert_invalid(session, query, matching=None, expected=InvalidRequest):
    """
    Attempt to issue a query and assert that the query is invalid.
    @param session Session to use
    @param query Invalid query to run
    @param matching Optional error message string contained within expected exception
    @param expected Exception expected to be raised by the invalid query

    Examples:
    assert_invalid(session, 'DROP USER nonexistent', "nonexistent doesn't exist")
    """
    assert_exception(session, query, matching=matching, expected=expected)


def assert_unauthorized(session, query, message):
    """
    Attempt to issue a query, and assert Unauthorized is raised.
    @param session Session to use
    @param query Unauthorized query to run
    @param message Expected error message

    Examples:
    assert_unauthorized(session, "ALTER USER cassandra NOSUPERUSER", "You aren't allowed to alter your own superuser status")
    assert_unauthorized(cathy, "ALTER TABLE ks.cf ADD val int", "User cathy has no ALTER permission on <table ks.cf> or any of its parents")
    """
    assert_exception(session, query, matching=message, expected=Unauthorized)


def assert_one(session, query, expected, cl=None):
    """
    Assert query returns one row.
    @param session Session to use
    @param query Query to run
    @param expected Expected results from query
    @param cl Optional Consistency Level setting. Default ONE

    Examples:
    assert_one(session, "LIST USERS", ['cassandra', True])
    assert_one(session, query, [0, 0])
    """
    simple_query = SimpleStatement(query, consistency_level=cl)
    res = session.execute(simple_query)
    list_res = rows_to_list(res)
    assert list_res == [expected], "Expected {} from {}, but got {}".format([expected], query, list_res)

def assert_none(session, query, cl=None):
    """
    Assert query returns nothing
    @param session Session to use
    @param query Query to run
    @param cl Optional Consistency Level setting. Default ONE

    Examples:
    assert_none(self.session1, "SELECT * FROM test where key=2;")
    assert_none(cursor, "SELECT * FROM test WHERE k=2", cl=ConsistencyLevel.SERIAL)
    """
    simple_query = SimpleStatement(query, consistency_level=cl)
    res = session.execute(simple_query)
    list_res = rows_to_list(res)
    assert list_res == [], "Expected nothing from {}, but got {}".format(query, list_res)

def assert_all(session, query, expected, cl=None, ignore_order=False):
    """
    Assert query returns all expected items optionally in the correct order
    @param session Session in use
    @param query Query to run
    @param expected Expected results from query
    @param cl Optional Consistency Level setting. Default ONE
    @param ignore_order Optional boolean flag determining whether response is ordered

    Examples:
    assert_all(session, "LIST USERS", [['aleksey', False], ['cassandra', True]])
    assert_all(self.session1, "SELECT * FROM ttl_table;", [[1, 42, 1, 1]])
    """
    simple_query = SimpleStatement(query, consistency_level=cl)
    res = session.execute(simple_query)
    list_res = rows_to_list(res)
    if ignore_order:
        expected = sorted(expected)
        list_res = sorted(list_res)
    assert list_res == expected, "Expected {} from {}, but got {}".format(expected, query, list_res)


def assert_almost_equal(*args, **kwargs):
    """
    Assert variable number of arguments all fall within a margin of error.
    @params *args variable number of numerical arguments to check
    @params error Optional margin of error. Default 0.16
    @params error_message Optional error message to print. Default ''

    Examples:
    assert_almost_equal(sizes[2], init_size)
    assert_almost_equal(ttl_session1, ttl_session2[0][0], error=0.005)
    """
    error = kwargs['error'] if 'error' in kwargs else 0.16
    vmax = max(args)
    vmin = min(args)
    error_message = '' if 'error_message' not in kwargs else kwargs['error_message']
    assert vmin > vmax * (1.0 - error) or vmin == vmax, "values not within {.2f}% of the max: {} ({})".format(error * 100, args, error_message)


def assert_row_count(session, table_name, expected, where=None):
    """
    Assert the number of rows in a table matches expected.
    @params session Session to use
    @param table_name Name of the table to query
    @param expected Number of rows expected to be in table

    Examples:
    assert_row_count(self.session1, 'ttl_table', 1)
    """
    if where is not None:
        query = "SELECT count(*) FROM {} WHERE {};".format(table_name, where)
    else:
        query = "SELECT count(*) FROM {};".format(table_name)
    res = session.execute(query)
    count = res[0][0]
    assert count == expected, "Expected a row count of {} in table '{}', but got {}".format(
        expected, table_name, count
    )


def assert_crc_check_chance_equal(session, table, expected, ks="ks", view=False):
    """
    Assert crc_check_chance equals expected for a given table or view
    @param session Session to use
    @param table Name of the table or view to check
    @param ks Optional Name of the keyspace
    @param view Optional Boolean flag indicating if the table is a view

    Examples:
    assert_crc_check_chance_equal(session, "compression_opts_table", 0.25)
    assert_crc_check_chance_equal(session, "t_by_v", 0.5, view=True)

    driver still doesn't support top-level crc_check_chance property,
    so let's fetch directly from system_schema
    """
    if view:
        assert_one(session,
                   "SELECT crc_check_chance from system_schema.views WHERE keyspace_name = 'ks' AND "
                   "view_name = '{table}';".format(table=table),
                   [expected])
    else:
        assert_one(session,
                   "SELECT crc_check_chance from system_schema.tables WHERE keyspace_name = 'ks' AND "
                   "table_name = '{table}';".format(table=table),
                   [expected])


def assert_length_equal(object_with_length, expected_length):
    """
    Assert an object has a specific length.
    @param object_with_length The object whose length will be checked
    @param expected_length The expected length of the object

    Examples:
    assert_length_equal(res, nb_counter)
    """
    assert_equal(len(object_with_length), expected_length, object_with_length)
