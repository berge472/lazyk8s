

def alignText(text: str, width: int, alignment: str = 'left', trimFromFront: bool = False, truncationIndicator: str = "..") -> str:
    """Aligns text to a given width by padding with spaces or trimming as needed.

    Args:
        text (str): The text to align.
        width (int): The desired width of the output text.
        alignment (str, optional): The alignment type ('left', 'right', 'center'). Defaults to 'left'.
        trimFromBack (bool, optional): If True, trims excess characters from the back. Defaults to False.
        truncationIndicator (str, optional): The string to indicate truncation. Defaults to "..".
    Returns:
        str: The aligned text.
    """

    if len(text) > width:
        if trimFromFront:
            return truncationIndicator + text[-(width - len(truncationIndicator)):]
        else:
            return text[:width - len(truncationIndicator)] + truncationIndicator
    elif len(text) < width:
        padding = width - len(text)
        if alignment == 'left':
            return text + ' ' * padding
        elif alignment == 'right':
            return ' ' * padding + text
        elif alignment == 'center':
            left_padding = padding // 2
            right_padding = padding - left_padding
            return ' ' * left_padding + text + ' ' * right_padding
    return text

    