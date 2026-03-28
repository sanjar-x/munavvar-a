from collections.abc import Sequence

type Paginated[T] = tuple[int, Sequence[T]]
