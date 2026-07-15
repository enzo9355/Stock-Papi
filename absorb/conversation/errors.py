class ConversationError(Exception):
    """Safe base error for the conversational boundary."""


class InputRejected(ConversationError):
    pass


class ToolRejected(ConversationError):
    pass


class ToolUnavailable(ConversationError):
    pass


class ModelUnavailable(ConversationError):
    pass
