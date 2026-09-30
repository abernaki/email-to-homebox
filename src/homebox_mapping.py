"""Pure helpers for mapping extracted receipt items to Homebox payloads."""


def sanitize_item_name(name):
    """Remove trademark/copyright symbols and normalize whitespace."""
    if not name:
        return name

    for char in ('™', '®', '©'):
        name = name.replace(char, '')

    return ' '.join(name.split())


def map_to_homebox_item(item, receipt_data, config, location_id):
    """Map extracted item data to the payload accepted by Homebox."""
    category = item.get('category', 'other')
    config['homebox']['category_map'].get(category, 'General')

    notes = config['homebox']['notes_template'].format(
        store=receipt_data.get('store', 'Unknown'),
        date=receipt_data.get('order_date', 'Unknown'),
        order_id=receipt_data.get('order_id', 'N/A')
    )

    if item.get('description'):
        notes = f"{item['description']}\n\n{notes}"

    homebox_item = {
        'name': sanitize_item_name(item['name']),
        'description': notes,
        'quantity': item.get('quantity', 1),
        'locationId': location_id
    }

    if item.get('price') and item['price'] > 0:
        homebox_item['purchasePrice'] = float(item['price'])

    if receipt_data.get('store'):
        homebox_item['purchaseFrom'] = receipt_data['store']

    if receipt_data.get('order_date'):
        homebox_item['purchaseTime'] = receipt_data['order_date']

    if item.get('manufacturer'):
        homebox_item['manufacturer'] = item['manufacturer']

    if item.get('model_number'):
        homebox_item['modelNumber'] = item['model_number']

    if item.get('serial_number'):
        homebox_item['serialNumber'] = item['serial_number']

    return homebox_item
