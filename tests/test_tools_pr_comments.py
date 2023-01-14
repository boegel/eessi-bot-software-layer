# Tests for functions defined in 'tools/pr_comments.py' of the EESSI
# build-and-deploy bot, see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Thomas Roeblitz (@trz42)
# author: Kenneth Hoste (@boegel)
#
# license: GPLv2
#

# Standard library imports
import os
import re
from unittest.mock import patch

# Third party imports (anything installed into the local Python environment)
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools.pr_comments import get_comment, get_submitted_job_comment, update_comment


class MockIssueComment:
    def __init__(self, body, edit_raises=None):
        self.body = body
        self.edit_raises = edit_raises

    def edit(self, body):
        if self.edit_raises:
            raise self.edit_raises
        self.body = body


class GetIssueCommentException(Exception):
    "Raised when pr.get_issue_comment fails in a test."
    pass


class EditIssueCommentException(Exception):
    "Raised when issue_comment.edit fails in a test."
    pass


@pytest.fixture
def get_issue_comments_raise_exception():
    with patch('github.PullRequest.PullRequest') as mock_pr:
        instance = mock_pr.return_value
        instance.get_issue_comments.side_effect = GetIssueCommentException()
        instance.get_issue_comments.return_value = ()
        yield instance


@pytest.fixture
def pr_no_comments():
    with patch('github.PullRequest.PullRequest') as mock_pr:
        instance = mock_pr.return_value
        instance.get_issue_comments.return_value = ()
        yield instance


@pytest.fixture
def pr_single_comment():
    with patch('github.PullRequest.PullRequest') as mock_pr:
        instance = mock_pr.return_value
        instance._issue_comments = [MockIssueComment("foo")]
        instance.get_issue_comments.return_value = instance._issue_comments
        # always returns first element. can this depend on the argument
        # provided to the function get_issue_comment?
        instance.get_issue_comment.return_value = instance._issue_comments[0]
        yield instance


@pytest.fixture
def pr_single_comment_failing():

    issue_comments = [MockIssueComment("foo")]

    def should_raise_exception():
        """
        Determine whether or not an exception should be raised, based on value of $TEST_RAISE_EXCEPTION
        """
        should_raise = False

        test_raise_exception = os.getenv('TEST_RAISE_EXCEPTION')
        count_regex = re.compile('^[0-9]+$')

        if test_raise_exception == 'always_raise':
            should_raise = True
        # if $TEST_RAISE_EXCEPTION is a number, eaise exception when > 0 and decrement with 1
        elif count_regex.match(test_raise_exception):
            test_raise_exception = int(test_raise_exception)
            if test_raise_exception > 0:
                should_raise = True
                os.environ['TEST_RAISE_EXCEPTION'] = str(test_raise_exception - 1)

        return should_raise

    def get_issue_comments_maybe_raise_exception():
        if should_raise_exception():
            raise GetIssueCommentException

        return issue_comments

    def get_issue_comment_maybe_raise_exception():
        if should_raise_exception():
            raise GetIssueCommentException

        # always returns first element. can this depend on the argument
        # provided to the function get_issue_comment?
        return issue_comments[0]

    with patch('github.PullRequest.PullRequest') as mock_pr:
        instance = mock_pr.return_value
        instance._issue_comments = [MockIssueComment("foo")]
        instance.get_issue_comments.side_effect = get_issue_comments_maybe_raise_exception
        instance.get_issue_comment.side_effect = get_issue_comment_maybe_raise_exception

        yield instance


# cases:
#  - no comments exist
#  - search string should be found
#  - search string should not be found
#  - calling get_issue_comments raises an Exception
def test_get_comment_no_comment(pr_no_comments):
    expected = None
    actual = get_comment(pr_no_comments, "foo")
    assert expected == actual


def test_get_comment_found(pr_single_comment):
    expected = MockIssueComment("foo").body
    actual = get_comment(pr_single_comment, "foo").body
    assert expected == actual


def test_get_comment_not_found(pr_single_comment):
    expected = None
    actual = get_comment(pr_single_comment, "bar")
    assert expected == actual


def test_get_comment_exception(get_issue_comments_raise_exception):
    with pytest.raises(Exception):
        get_comment(get_issue_comments_raise_exception, "bar")


def test_get_submitted_job_comment_exception(get_issue_comments_raise_exception):
    with pytest.raises(Exception):
        get_submitted_job_comment(get_issue_comments_raise_exception, 42)


def test_get_comment_retry(pr_single_comment_failing):
    expected = MockIssueComment("foo").body

    # test whether get_comment retries multiple times when problems occur when getting the comment;
    # start with specifying that getting the comment should always fail
    os.environ['TEST_RAISE_EXCEPTION'] = 'always_raise'
    with pytest.raises(Exception) as err:
        get_comment(pr_single_comment_failing, "foo")
    assert err.type == GetIssueCommentException

    # getting comment should succeed on 2nd try (fail once)
    os.environ['TEST_RAISE_EXCEPTION'] = '1'
    expected = "foo"
    actual = get_comment(pr_single_comment_failing, "foo").body
    assert expected == actual

    # getting comment should fail 3 times, and get_comment only retries twice,
    # so get_comment should fail with exception
    os.environ['TEST_RAISE_EXCEPTION'] = '3'
    with pytest.raises(Exception) as err:
        get_comment(pr_single_comment_failing, "foo")
    assert err.type == GetIssueCommentException


# test cases:
#  - pr.get_issue_comment(cmnt_id) succeeds
#    C1: returns obj with edit & body -> edit is called (and succeeds, see C4)
#    C2: returns None -> edit is not called, log message is written
#  - pr.get_issue_comment(cmnt_id) fails (e.g., connection error)
#    . fails 1,...,n times (n > tries) --> should it raise a specific Exception (to indicate
#      that the first command failed)?
#    C3.1 - not implemented yet
#    C3.n
#  - issue_comment.edit(...) succeeds (side effect: body is changed)
#    C4: included in C1
#  - issue_comment.edit(...) fails (connection error, called with incompatible types)
#    . fails 1,...,n times (n > tries) --> should it raise a specific Exception (to indicate
#      that the second command failed)?
#    C5.1 - not implemented yet
#    C5.n
#    C6.1 - not implemented yet
#    C6.n
#


def test_get_issue_comment_succeeds_none(tmpdir):
    log_file = os.path.join(tmpdir, "log.txt")
    with patch('github.PullRequest.PullRequest') as mock_pr:
        instance = mock_pr.return_value
        instance.get_issue_comment.return_value = None

        cmnt_id = 0
        update = "body-0"
        update_comment(cmnt_id, instance, update, log_file=log_file)

        # log_file should exists
        assert os.path.exists(log_file)

        # log_file should contain error message ""
        expected = f"no comment with id {cmnt_id}, skipping update '{update}'"
        file = tmpdir.join("log.txt")
        actual = file.read()
        # actual log message starts with a timestamp, hence we use 'in'
        assert expected in actual


def test_get_issue_comment_succeeds_one_comment(tmpdir):
    log_file = os.path.join(tmpdir, "log.txt")
    comment_to_update = MockIssueComment("__ORG-comment__")
    with patch('github.PullRequest.PullRequest') as mock_pr:
        instance = mock_pr.return_value
        instance.get_issue_comment.return_value = comment_to_update

        cmnt_id = 0
        update = "body-0"
        update_comment(cmnt_id, instance, update, log_file=log_file)

        # log_file should not exists
        assert not os.path.exists(log_file)

        # check body of updated comment
        expected = "__ORG-comment__body-0"
        actual = comment_to_update.body
        assert expected == actual


def test_get_issue_comment_fails(tmpdir):
    log_file = os.path.join(tmpdir, "log.txt")
    with patch('github.PullRequest.PullRequest') as mock_pr:
        instance = mock_pr.return_value
        instance.get_issue_comment.side_effect = GetIssueCommentException

        cmnt_id = -1
        update = "raise GetIssueCommentException"
        with pytest.raises(Exception):
            update_comment(cmnt_id, instance, update, log_file=log_file)

        # log_file should not exists
        assert not os.path.exists(log_file)

        # check if function was retried x times
        expected = 3
        actual = instance.get_issue_comment.call_count
        assert expected == actual


def test_issue_comment_edit_fails_exception(tmpdir):
    log_file = os.path.join(tmpdir, "log.txt")
    comment_to_update = MockIssueComment(
                            "__ORG-comment__",
                            edit_raises=EditIssueCommentException
                        )
    with patch('github.PullRequest.PullRequest') as mock_pr:
        instance_pr = mock_pr.return_value
        instance_pr.get_issue_comment.return_value = comment_to_update

        cmnt_id = 0
        update = "raise EditIssueCommentException"
        with pytest.raises(Exception):
            update_comment(cmnt_id, instance_pr, update, log_file=log_file)

        # log_file should not exists
        assert not os.path.exists(log_file)

        # check that body has not been updated
        expected = "__ORG-comment__"
        actual = comment_to_update.body
        assert expected == actual

        # check if function was retried x times
        expected = 3
        actual = instance_pr.get_issue_comment.call_count
        assert expected == actual


def test_issue_comment_edit_fails_args(tmpdir):
    log_file = os.path.join(tmpdir, "log.txt")
    comment_to_update = MockIssueComment("__ORG-comment__")
    with patch('github.PullRequest.PullRequest') as mock_pr:
        instance_pr = mock_pr.return_value
        instance_pr.get_issue_comment.return_value = comment_to_update
        # instance_ic = mock_ic.return_value

        cmnt_id = 0
        update = 42
        with pytest.raises(Exception):
            update_comment(cmnt_id, instance_pr, update, log_file=log_file)

        # log_file should not exists
        assert not os.path.exists(log_file)

        # check that body has not been updated
        expected = "__ORG-comment__"
        actual = comment_to_update.body
        assert expected == actual

        # check if function was retried x times
        expected = 3
        actual = instance_pr.get_issue_comment.call_count
        assert expected == actual
