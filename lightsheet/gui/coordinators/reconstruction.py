"""Pure-numpy image reconstruction helpers.

These were extracted from ``FrameSaverController`` so they can be tested
and used without the full Qt/QObject stack.
"""

from __future__ import annotations

import numpy as np


def _position_to_float(value: str | float) -> float:
    """Coerce a motor-position entry to ``float``. Strips trailing unit
    suffix from formatted display strings (e.g. ``"99.82 μm"``). Raises
    ``ValueError`` if the leading token is not numeric.
    """
    if isinstance(value, (int, float)):
        return float(value)
    token = str(value).strip().split()[0]
    return float(token)


def crop_buffer(buffer: np.ndarray) -> np.ndarray:
    """Crops each frame of a buffer with 20% frame-to-frame overlap"""

    image_xsize = buffer.shape[2]
    image_ysize = buffer.shape[1]
    tile_count = buffer.shape[0]

    if tile_count == 1:
        cropped_buffer = buffer
    else:
        tile_width = int(image_xsize / tile_count)
        tile_width_overlap = int(tile_width * 0.2)

        # Initializing empty cropped buffer
        cropped_buffer = np.zeros(
            (tile_count, image_ysize, tile_width + (2 * tile_width_overlap)),
            np.uint16,
        )

        # Crop with overlap
        for frame in range(tile_count):
            # NOTE - disabled intensity normalization
            # # Uniformize frame intensities
            # # average = np.average(buffer[frame,0:100,:]) #Average the  first rows
            # if frame == 0:
            #     reference_average = average
            # else:
            #     average_ratio = reference_average/average
            #     # buffer[frame,:,:] = buffer[frame,:,:] * average_ratio

            first_column = int(frame * tile_width - tile_width_overlap)
            next_first_column = int(
                first_column + tile_width + (2 * tile_width_overlap)
            )
            if frame == 0:  # For the first column step
                cropped_buffer[frame, :, tile_width_overlap:] = buffer[
                    frame, :, 0 : tile_width + tile_width_overlap
                ]
            elif (
                frame == tile_count - 1
            ):  # For the last column step (may be different than the others...)
                last_column_step = int(image_xsize - first_column)
                cropped_buffer[frame, :, 0:last_column_step] = buffer[
                    frame, :, first_column:
                ]
            else:
                cropped_buffer[frame, :, :] = buffer[
                    frame, :, first_column:next_first_column
                ]
    return cropped_buffer


def reconstruct_frame(buffer: np.ndarray) -> np.ndarray:
    """Reconstructs frame from buffer"""

    image_xsize = buffer.shape[2]
    image_ysize = buffer.shape[1]
    tile_count = buffer.shape[0]

    # Initializing empty frame
    reconstructed_frame = np.zeros((image_ysize, image_xsize), np.uint16)

    # Crops each frame of a buffer with no overlap and merge
    if tile_count == 1:
        reconstructed_frame = buffer[0, :, :]
    else:
        tile_width = int(image_xsize / tile_count)

        for frame in range(tile_count):
            # NOTE - disabled intensity normalization
            # # Uniformize frame intensities
            # # average = np.average(buffer[frame,0:100,:]) #Average the  first rows
            # if frame == 0:
            #     reference_average = average
            # else:
            #     average_ratio = reference_average/average
            #     #print('average_ratio:'+str(average_ratio))
            #     # buffer[frame,:,:] = buffer[frame,:,:] * average_ratio

            # Reconstruct frame
            first_column = frame * tile_width
            next_first_column = first_column + tile_width
            if (
                frame == tile_count - 1
            ):  # For the last column step (may be different than the others...)
                reconstructed_frame[:, first_column:] = buffer[
                    frame, :, first_column:
                ]
            else:
                reconstructed_frame[:, first_column:next_first_column] = buffer[
                    frame, :, first_column:next_first_column
                ]
    return reconstructed_frame


def reconstruct_frame_linear_blend(buffer: np.ndarray) -> np.ndarray:
    """Reconstructs frame from buffer using linear blend over 20% overlap"""

    image_xsize = buffer.shape[2]
    image_ysize = buffer.shape[1]
    tile_count = buffer.shape[0]

    # Initializing empty output frame
    reconstructed_frame = np.zeros((image_ysize, image_xsize), np.uint16)

    if tile_count == 1:
        reconstructed_frame = buffer[0, :, :]
    else:
        # Crops each frame of a buffer with 20% overlap for futher frame reconstruction  # noqa: E501
        tile_width = int(image_xsize / tile_count)
        tile_width_overlap = int(tile_width * 0.2)

        # Initializing empty cropped buffer
        cropped_buffer = np.zeros(
            (tile_count, image_ysize, tile_width + (2 * tile_width_overlap)),
            np.uint16,
        )

        # Crop with overlap
        for frame in range(tile_count):
            first_column = int(frame * tile_width - tile_width_overlap)
            next_first_column = int(
                first_column + tile_width + (2 * tile_width_overlap)
            )
            if frame == 0:  # For the first column step
                cropped_buffer[frame, :, tile_width_overlap:] = buffer[
                    frame, :, 0 : tile_width + tile_width_overlap
                ]
            elif (
                frame == tile_count - 1
            ):  # For the last column step (may be different than the others...)
                last_column_step = int(image_xsize - first_column)
                cropped_buffer[frame, :, 0:last_column_step] = buffer[
                    frame, :, first_column:
                ]
            else:
                cropped_buffer[frame, :, :] = buffer[
                    frame, :, first_column:next_first_column
                ]

        # Reconstruct frame with linear blend for overlapping region
        weight_step = 1 / (2 * tile_width_overlap)

        for frame in range(tile_count):
            first_center_column = int(frame * tile_width + tile_width_overlap)
            last_center_column = int((frame + 1) * tile_width - tile_width_overlap)
            previous_last_center_column = int(
                frame * tile_width - tile_width_overlap
            )

            if frame == 0:  # For the first column step
                reconstructed_frame[:, 0:last_center_column] = cropped_buffer[
                    frame, :, tile_width_overlap:tile_width
                ]
            else:
                for column in range(2 * tile_width_overlap):
                    frame_column = column + previous_last_center_column
                    last_buffer_column = column + tile_width
                    buffer_weight = column * weight_step
                    last_buffer_weight = 1 - column * weight_step
                    reconstructed_frame[:, frame_column] = (
                        buffer_weight * cropped_buffer[frame, :, column]
                        + last_buffer_weight
                        * cropped_buffer[(frame - 1), :, last_buffer_column]
                    )
                if (
                    frame == tile_count - 1
                ):  # For the last column step (may be different than the others...)
                    last_column_step = int(image_xsize - first_center_column)
                    reconstructed_frame[:, first_center_column:] = cropped_buffer[
                        frame,
                        :,
                        (2 * tile_width_overlap) : (2 * tile_width_overlap)
                        + last_column_step,
                    ]
                else:
                    reconstructed_frame[
                        :, first_center_column:last_center_column
                    ] = cropped_buffer[
                        frame, :, (2 * tile_width_overlap) : tile_width
                    ]
    return reconstructed_frame
