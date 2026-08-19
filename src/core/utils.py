from typing import Any, TypeVar, List

T = TypeVar("T")

def chunk_list(items: List[T], size: int) -> List[List[T]]:
    """
    Splits a list into chunks of a given maximum size.
    
    Args:
        items: The list to chunk.
        size: The maximum size of each chunk.
        
    Returns:
        A list of sublists where each sublist has length <= size.
    """
    if size <= 0:
        return [items]
    return [items[i:i + size] for i in range(0, len(items), size)]
